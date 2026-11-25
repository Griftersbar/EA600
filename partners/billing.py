from datetime import datetime, timezone as utc
from uuid import UUID, uuid4

from django.conf import settings
from django.db.models import Q
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from stripe import StripeClient

from .models import PartnerApplication


PLANS = {"monthly": ("month", 1200), "annual": ("year", 12000)}


class BillingUnavailable(Exception):
    pass


def price_id(plan):
    return {"monthly": settings.STRIPE_TEST_MONTHLY_PRICE, "annual": settings.STRIPE_TEST_ANNUAL_PRICE}.get(plan, "")


def billing_ready():
    return bool(
        settings.STRIPE_TEST_SECRET_KEY.startswith(("sk_test_", "rk_test_"))
        and settings.STRIPE_TEST_WEBHOOK_SECRET.startswith("whsec_")
        and all(price_id(plan).startswith("price_") for plan in PLANS)
    )


def stripe_client():
    return StripeClient(settings.STRIPE_TEST_SECRET_KEY, max_network_retries=2)


def checkout(application, plan, return_url):
    """Reuse the unpaid session or reserve exactly one Stripe attempt per application."""
    client = stripe_client()
    if not application.can_checkout:
        return None

    if application.checkout_id:
        session = client.v1.checkout.sessions.retrieve(application.checkout_id)
        if session.get("status") == "open":
            if application.checkout_plan == plan:
                return session.get("url")
            session = client.v1.checkout.sessions.expire(application.checkout_id)
        if session.get("status") == "complete" and not application.stripe_subscription_id:
            confirm_checkout(session)
            return None
        if session.get("status") != "expired" and application.billing_status not in application.ENDED_STATUSES:
            return None
        rotated = PartnerApplication.objects.filter(pk=application.pk, checkout_attempt=application.checkout_attempt).update(
            checkout_attempt=uuid4(), checkout_id="", checkout_plan="", stripe_subscription_id=None,
            billing_status="", paid_until=None, synced_at=None,
        )
        if not rotated:
            raise BillingUnavailable("The checkout changed. Please try again.")
        application.refresh_from_db()

    if not application.checkout_plan:
        PartnerApplication.objects.filter(pk=application.pk, checkout_attempt=application.checkout_attempt, checkout_plan="").update(
            checkout_plan=plan,
        )
        application.refresh_from_db()
    if application.checkout_plan != plan:
        raise BillingUnavailable(f"Your {application.checkout_plan} checkout is being prepared. Continue with that plan.")

    interval, amount = PLANS[plan]
    price = client.v1.prices.retrieve(price_id(plan))
    recurring = price.get("recurring") or {}
    if (price.get("livemode") is not False or not price.get("active") or price.get("currency") != "gbp"
            or price.get("unit_amount") != amount or recurring.get("interval") != interval
            or recurring.get("interval_count") != 1 or recurring.get("usage_type") != "licensed"):
        raise BillingUnavailable("The test price doesn’t match this plan.")

    metadata = {"application": str(application.pk), "attempt": str(application.checkout_attempt)}
    customer = {"customer": application.stripe_customer_id} if application.stripe_customer_id else {"customer_email": application.owner.email}
    session = client.v1.checkout.sessions.create({
        **customer,
        "mode": "subscription",
        "payment_method_types": ["card"],
        "line_items": [{"price": price_id(plan), "quantity": 1}],
        "client_reference_id": str(application.pk),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "success_url": return_url + "?checkout=returned",
        "cancel_url": return_url + "?checkout=paused",
    }, options={"idempotency_key": f"ea600-checkout-{application.checkout_attempt}"})
    PartnerApplication.objects.filter(pk=application.pk, checkout_attempt=application.checkout_attempt).update(checkout_id=session.id)
    return session.url


def confirm_checkout(session):
    metadata = session.get("metadata") or {}
    if session.get("livemode") is not False or session.get("mode") != "subscription" or not session.get("subscription"):
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
        pk=application_id, checkout_attempt=attempt, checkout_plan__in=PLANS,
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


def sync_subscription(application, subscription_id):
    observed_at = timezone.now()
    subscription = stripe_client().v1.subscriptions.retrieve(subscription_id, {"expand": ["latest_invoice"]})
    metadata = subscription.get("metadata") or {}
    if (subscription.get("livemode") is not False or metadata.get("application") != str(application.pk)
            or metadata.get("attempt") != str(application.checkout_attempt)):
        return

    items = subscription["items"]["data"]
    invoice = subscription.get("latest_invoice") or {}
    status = subscription["status"]
    correct_price = len(items) == 1 and items[0]["price"]["id"] == price_id(application.checkout_plan) and items[0]["quantity"] == 1
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
    PartnerApplication.objects.filter(
        Q(synced_at__lt=observed_at) | Q(synced_at__isnull=True),
        Q(stripe_subscription_id=subscription_id) | Q(stripe_subscription_id__isnull=True),
        pk=application.pk, checkout_attempt=application.checkout_attempt,
    ).update(**updates)


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
        application = PartnerApplication.objects.filter(stripe_subscription_id=subscription_id).first()
        if application:
            sync_subscription(application, subscription_id)
