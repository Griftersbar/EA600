from datetime import datetime, timezone as utc
from uuid import UUID, uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from stripe import StripeClient

from .models import AdvertisePageSettings, PartnerApplication
from .notifications import notify_listing_live


# Keep the original amounts for unfinished checkouts created before Wagtail pricing.
PLANS = {"monthly": ("month", 1200), "annual": ("year", 12000)}


def plan_amounts(page):
    return {"monthly": page.monthly_price, "annual": page.annual_price}


def display_prices(page):
    return {plan: f"£{amount:.2f}".removesuffix(".00") for plan, amount in plan_amounts(page).items()}


class BillingUnavailable(Exception):
    pass


def live_billing():
    return settings.PARTNER_BILLING_MODE == PartnerApplication.BillingMode.LIVE


def secret_key():
    return settings.STRIPE_LIVE_SECRET_KEY if live_billing() else settings.STRIPE_TEST_SECRET_KEY


def webhook_secret():
    return settings.STRIPE_LIVE_WEBHOOK_SECRET if live_billing() else settings.STRIPE_TEST_WEBHOOK_SECRET


def price_id(plan):
    if live_billing():
        return {"monthly": settings.STRIPE_LIVE_MONTHLY_PRICE, "annual": settings.STRIPE_LIVE_ANNUAL_PRICE}[plan]
    return {"monthly": settings.STRIPE_TEST_MONTHLY_PRICE, "annual": settings.STRIPE_TEST_ANNUAL_PRICE}[plan]


def billing_ready():
    prefixes = ("sk_live_", "rk_live_") if live_billing() else ("sk_test_", "rk_test_")
    return bool(
        settings.PARTNER_BILLING_MODE in PartnerApplication.BillingMode.values
        and secret_key().startswith(prefixes)
        and webhook_secret().startswith("whsec_")
        and all(price_id(plan).startswith("price_") for plan in PLANS)
    )


def stripe_client():
    return StripeClient(secret_key(), max_network_retries=2)


def is_recurring_price(price, plan):
    recurring = price.get("recurring") or {}
    return (
        price.get("livemode") is live_billing() and price.get("currency") == "gbp"
        and recurring.get("interval") == PLANS[plan][0]
        and recurring.get("interval_count") == 1 and recurring.get("usage_type") == "licensed"
    )


def reserved_amount(application):
    if application.checkout_amount_pence is not None:
        return application.checkout_amount_pence
    return PLANS[application.checkout_plan][1]


def checkout_item(client, application):
    plan = application.checkout_plan
    configured_price_id = price_id(plan)
    price = client.v1.prices.retrieve(configured_price_id)
    if not is_recurring_price(price, plan) or not price.get("active"):
        raise BillingUnavailable("The Stripe price must be an active GBP price for this billing interval.")

    amount = reserved_amount(application)
    if price.get("unit_amount") == amount:
        return {"price": configured_price_id, "quantity": 1}

    # An older reserved attempt must retain its original Stripe request on retry.
    if application.checkout_amount_pence is None:
        raise BillingUnavailable("The Stripe price does not match the reserved checkout.")
    product = price.get("product")
    if not isinstance(product, str) or not product.startswith("prod_"):
        raise BillingUnavailable("The Stripe price must belong to a product.")
    return {"price_data": {
        "currency": "gbp", "product": product, "unit_amount": amount,
        "recurring": {"interval": PLANS[plan][0]},
    }, "quantity": 1}


def checkout(application, plan, return_url, cancel_url):
    """Reuse the unpaid session or reserve exactly one Stripe attempt per application."""
    if not application.can_checkout:
        return None
    if not application.has_current_billing_mode:
        # A previous sandbox checkout has no payment or customer IDs in live Stripe.
        PartnerApplication.objects.filter(
            pk=application.pk, billing_mode=PartnerApplication.BillingMode.TEST,
        ).update(
            billing_mode=PartnerApplication.BillingMode.LIVE, checkout_attempt=uuid4(),
            checkout_id="", checkout_plan="", checkout_amount_pence=None, stripe_customer_id="",
            stripe_subscription_id=None, billing_status="", paid_until=None, synced_at=None,
        )
        application.refresh_from_db()
        if not application.has_current_billing_mode or not application.can_checkout:
            return None

    current = PartnerApplication.objects.filter(pk=application.pk, billing_mode=settings.PARTNER_BILLING_MODE)
    client = stripe_client()
    new_amount = int(plan_amounts(AdvertisePageSettings.load())[plan] * 100)
    if application.checkout_id:
        session = client.v1.checkout.sessions.retrieve(application.checkout_id)
        if session.get("status") == "open":
            if application.checkout_plan == plan and reserved_amount(application) == new_amount:
                return session.get("url")
            session = client.v1.checkout.sessions.expire(application.checkout_id)
        if session.get("status") == "complete" and not application.stripe_subscription_id:
            confirm_checkout(session)
            return None
        if session.get("status") != "expired" and application.billing_status not in application.ENDED_STATUSES:
            return None
        rotated = current.filter(checkout_attempt=application.checkout_attempt).update(
            checkout_attempt=uuid4(), checkout_id="", checkout_plan="", stripe_subscription_id=None,
            checkout_amount_pence=None, billing_status="", paid_until=None, synced_at=None,
        )
        if not rotated:
            raise BillingUnavailable("The checkout changed. Please try again.")
        application.refresh_from_db()

    if not application.checkout_plan:
        current.filter(checkout_attempt=application.checkout_attempt, checkout_plan="").update(
            checkout_plan=plan, checkout_amount_pence=new_amount,
        )
        application.refresh_from_db()
    if not application.has_current_billing_mode:
        return None
    if application.checkout_plan != plan:
        raise BillingUnavailable(f"Your {application.checkout_plan} checkout is being prepared. Continue with that plan.")

    metadata = {"application": str(application.pk), "attempt": str(application.checkout_attempt)}
    customer = {"customer": application.stripe_customer_id} if application.stripe_customer_id else {"customer_email": application.owner.email}
    session = client.v1.checkout.sessions.create({
        **customer,
        "mode": "subscription",
        "payment_method_types": ["card"],
        "line_items": [checkout_item(client, application)],
        "client_reference_id": str(application.pk),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "success_url": return_url + "?checkout=returned",
        "cancel_url": cancel_url,
    }, options={"idempotency_key": f"ea600-checkout-{application.checkout_attempt}"})
    if not current.filter(checkout_attempt=application.checkout_attempt).update(checkout_id=session.id):
        raise BillingUnavailable("The checkout changed. Please try again.")
    return session.url


def confirm_checkout(session):
    metadata = session.get("metadata") or {}
    if session.get("livemode") is not live_billing() or session.get("mode") != "subscription" or not session.get("subscription"):
        return
    try:
        application_id = UUID(metadata.get("application") or "")
        attempt = UUID(metadata.get("attempt") or "")
    except (TypeError, ValueError):
        return
    if session.get("client_reference_id") != str(application_id):
        return
    candidates = PartnerApplication.objects.filter(
        Q(checkout_id="") | Q(checkout_id=session["id"]),
        Q(stripe_subscription_id=None) | Q(stripe_subscription_id=session["subscription"]),
        pk=application_id, checkout_attempt=attempt, checkout_plan__in=PLANS, billing_mode=settings.PARTNER_BILLING_MODE,
    )
    if candidates.update(checkout_id=session["id"], stripe_subscription_id=session["subscription"]):
        application = candidates.first()
        if application:
            sync_subscription(application, session["subscription"])


def paid_invoice_end(invoice, item_id):
    if invoice.get("status") != "paid":
        return None
    ends = []
    for line in (invoice.get("lines") or {}).get("data", []):
        details = (line.get("parent") or {}).get("subscription_item_details") or {}
        end = (line.get("period") or {}).get("end")
        if details.get("subscription_item") == item_id and not details.get("proration") and end:
            ends.append(end)
    return datetime.fromtimestamp(max(ends), tz=utc.utc) if ends else None


def matches_subscription_price(application, item):
    if item["quantity"] != 1:
        return False
    price = item["price"]
    plan = application.checkout_plan
    if application.checkout_amount_pence is None:
        return price["id"] == price_id(plan)
    return is_recurring_price(price, plan) and price.get("unit_amount") == application.checkout_amount_pence


def sync_subscription(application, subscription_id):
    observed_at = timezone.now()
    subscription = stripe_client().v1.subscriptions.retrieve(subscription_id, {"expand": ["latest_invoice"]})
    metadata = subscription.get("metadata") or {}
    if (subscription.get("livemode") is not live_billing() or metadata.get("application") != str(application.pk)
            or metadata.get("attempt") != str(application.checkout_attempt)):
        return

    items = subscription["items"]["data"]
    invoice = subscription.get("latest_invoice") or {}
    status = subscription["status"]
    correct_price = len(items) == 1 and matches_subscription_price(application, items[0])
    updates = {
        "stripe_customer_id": subscription["customer"],
        "stripe_subscription_id": subscription_id,
        "billing_status": status if correct_price else "invalid_price",
        "synced_at": observed_at,
    }
    # Stripe's current subscription period can advance before the invoice is paid.
    if correct_price and status in application.BILLABLE_STATUSES:
        paid_end = paid_invoice_end(invoice, items[0]["id"])
        if paid_end:
            updates["paid_until"] = Greatest(Coalesce("paid_until", paid_end), paid_end)
    updated = PartnerApplication.objects.filter(
        Q(synced_at__lt=observed_at) | Q(synced_at__isnull=True),
        Q(stripe_subscription_id=subscription_id) | Q(stripe_subscription_id__isnull=True),
        pk=application.pk, checkout_attempt=application.checkout_attempt, billing_mode=settings.PARTNER_BILLING_MODE,
    ).update(**updates)
    if updated:
        transaction.on_commit(lambda: notify_listing_live(application.pk))


def apply_event(event):
    event_type = event["type"]
    data = event["data"]["object"]
    if event_type == "checkout.session.completed":
        confirm_checkout(data)
        return
    if event_type in {"invoice.paid", "invoice.payment_failed"}:
        details = (data.get("parent") or {}).get("subscription_details") or {}
        subscription_id = details.get("subscription") or data.get("subscription")
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = data["id"]
    else:
        return
    if subscription_id:
        application = PartnerApplication.objects.filter(
            stripe_subscription_id=subscription_id, billing_mode=settings.PARTNER_BILLING_MODE,
        ).first()
        if application:
            sync_subscription(application, subscription_id)
