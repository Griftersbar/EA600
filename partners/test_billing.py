import hashlib
import hmac
import json
import time
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY

from siteapp.models import Tour
from siteapp.test_support import sign_in_verified

from .models import AdvertisePageSettings, BusinessListing, PartnerAccount, PartnerApplication, PendingPartnerApplication, published_placements
from .views import OWNER_SESSION


@override_settings(
    PARTNER_APPLICATIONS_ENABLED=True, EMAIL_HOST="smtp.example.com",
    STRIPE_TEST_SECRET_KEY="sk_test_fixture", STRIPE_TEST_WEBHOOK_SECRET="whsec_fixture",
    STRIPE_TEST_MONTHLY_PRICE="price_month_fixture", STRIPE_TEST_ANNUAL_PRICE="price_year_fixture",
)
class PartnerBillingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tour = Tour.objects.get(slug="ea600")
        cls.stop = cls.tour.stops.get(title="Norwich")
        cls.editor = get_user_model().objects.create_superuser(username="partner-editor")

    def setUp(self):
        cache.clear()
        gateway = patch("partners.billing.stripe_client")
        self.stripe = gateway.start().return_value.v1
        self.addCleanup(gateway.stop)

    def apply_as_owner(self, *, placement=None, **fields):
        self.assertContains(self.client.post(reverse("partners:apply", query=placement), {
            "email": "Owner@Example.com",
            "name": "Norwich Test Tea Room", "category": "food", "description": "Tea and scones",
            "address": "Norwich, NR1", "stop": self.stop.pk, "link": "https://example.com/tea",
            "link_label": "website", **fields,
        }), "Check your inbox")
        self.assertEqual(mail.outbox[-1].to, ["owner@example.com"])
        self.assertEqual(mail.outbox[-1].subject, "Confirm your EA600 business email")
        self.assertFalse(PartnerApplication.objects.exists())
        access_url = urlsplit(mail.outbox[-1].body.split()[-1]).path
        self.assertContains(self.client.get(access_url), "Confirm and submit listing")
        self.assertFalse(PartnerApplication.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(access_url), reverse("partners:dashboard"))
        self.assertEqual(mail.outbox[-1].subject, "We received your EA600 listing application")
        self.assertContains(Client().post(access_url), "has already been used")
        self.assertFalse(PendingPartnerApplication.objects.exists())
        return PartnerApplication.objects.select_related("listing", "owner").get()

    def test_public_advertising_links_carry_the_route_or_destination(self):
        tour = Tour.objects.get(slug="ea600-14-day")
        destination = self.stop.destination
        route_apply = reverse("partners:apply", query={"route": tour.slug})
        destination_apply = reverse("partners:apply", query={"destination": destination.slug})

        self.assertContains(self.client.get(tour.get_absolute_url()), f'href="{route_apply}"')
        self.assertContains(self.client.get(destination.get_absolute_url()), f'href="{destination_apply}"')
        form = self.client.get(route_apply).context["form"]
        self.assertEqual(set(form.fields["stop"].queryset), set(tour.stops.all()))
        self.assertIsNone(form["stop"].value())

        form = self.client.get(destination_apply).context["form"]
        self.assertEqual(set(form.fields["stop"].queryset), set(destination.route_stops.filter(tour__is_published=True)))
        self.assertEqual(form["stop"].value(), self.stop.pk)

        response = self.client.post(route_apply, {"stop": self.stop.pk})
        self.assertTrue(response.context["form"].has_error("stop", "invalid_choice"))
        self.assertFalse(PendingPartnerApplication.objects.exists())

        tour.is_published = False
        tour.save(update_fields=["is_published"])
        form = self.client.get(route_apply).context["form"]
        self.assertFalse(form.placement_query)
        self.assertIn(self.stop, form.fields["stop"].queryset)
        self.assertFalse(form.fields["stop"].queryset.filter(tour=tour).exists())

    def test_signed_in_advertiser_keeps_the_preselected_destination(self):
        session = self.client.session
        session[OWNER_SESSION] = PartnerAccount.objects.create(email="owner@example.com").pk
        session.save()
        placement = {"destination": self.stop.destination.slug}
        dashboard = reverse("partners:dashboard", query=placement, fragment="apply-for-listing")
        self.assertRedirects(self.client.get(reverse("partners:apply", query=placement)), dashboard)
        response = self.client.get(dashboard)
        self.assertContains(response, 'id="apply-for-listing"')
        self.assertEqual(response.context["form"]["stop"].value(), self.stop.pk)

    def approve(self, application):
        listing = application.listing
        editor = Client()
        sign_in_verified(editor, self.editor)
        with self.captureOnCommitCallbacks(execute=True):
            response = editor.post(reverse("ea600_business_listings:edit", args=[listing.pk]), {
                "name": listing.name, "category": listing.category, "description": listing.description,
                "address": listing.address, "link": listing.link, "link_label": listing.link_label,
                "stops": [self.stop.pk], "action-publish": "1",
            })
        self.assertEqual(response.status_code, 302)
        listing.refresh_from_db()
        self.assertTrue(listing.live)
        self.assertEqual(mail.outbox[-1].subject, "Your EA600 business listing is approved")
        self.assertEqual(mail.outbox[-1].to, [application.owner.email])

    def configure_price(self, interval, amount, *, live=False):
        self.stripe.prices.retrieve.return_value = {
            "livemode": live, "active": True, "currency": "gbp", "unit_amount": amount,
            "product": "prod_listing_fixture",
            "recurring": {"interval": interval, "interval_count": 1, "usage_type": "licensed"},
        }
        self.stripe.checkout.sessions.create.return_value = SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/test")

    def signed_event(self, event_type, data, *, live=False, secret=b"whsec_fixture"):
        payload = json.dumps({"object": "event", "id": "evt_test", "type": event_type, "livemode": live, "data": {"object": data}})
        timestamp = int(time.time())
        signature = hmac.new(secret, f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
        return self.client.post(reverse("partners:webhook"), payload, content_type="application/json",
                                headers={"Stripe-Signature": f"t={timestamp},v1={signature}"})

    @override_settings(EA600_PUBLIC_DOMAIN="preview.example.com")
    def test_verified_application_approval_annual_checkout_and_payment_lifecycle(self):
        application = self.apply_as_owner(placement={"destination": self.stop.destination.slug})
        origin = "https://preview.example.com"
        self.assertIn(f"{origin}/advertise/apply/confirm/", mail.outbox[0].body)
        self.assertIn(f"{origin}/advertise/#business-listing-access", mail.outbox[1].body)
        listing = application.listing
        self.assertEqual(listing.stops.get(), self.stop)
        self.assertTrue(listing.requires_subscription)
        self.assertFalse(listing.live)
        checkout = reverse("partners:checkout", args=[application.pk])
        self.assertEqual(self.client.get(checkout).status_code, 409)
        self.assertEqual(self.client.post(checkout, {"plan": "annual"}).status_code, 409)
        self.assertEqual(Client().get(checkout).status_code, 404)
        self.assertEqual(Client().post(checkout, {"plan": "annual"}).status_code, 404)

        self.approve(application)
        payment_url = urlsplit(mail.outbox[-1].body.split()[-1])
        self.assertEqual((payment_url.scheme, payment_url.netloc), ("https", "preview.example.com"))
        pay_link = payment_url.path
        fresh_buyer = Client()
        self.assertContains(fresh_buyer.get(pay_link), "Continue to payment options")
        self.assertEqual(fresh_buyer.get(checkout).status_code, 404)
        self.assertRedirects(fresh_buyer.post(pay_link), checkout)
        self.assertContains(Client().post(pay_link), "has already been used")
        self.assertFalse(published_placements(self.tour).exists())
        self.configure_price("year", 12000)
        AdvertisePageSettings.objects.update(annual_price="145.25")
        self.assertContains(self.client.get(reverse("partners:dashboard")), "Choose a payment plan")
        payment = self.client.get(checkout)
        self.assertContains(payment, "Choose a listing subscription")
        self.assertContains(payment, "<strong>£145.25</strong> per year")
        self.assertContains(payment, "Test checkout")
        self.stripe.checkout.sessions.create.assert_not_called()
        self.assertRedirects(self.client.post(checkout, {"plan": "annual"}), "https://checkout.stripe.com/test", fetch_redirect_response=False)
        params = self.stripe.checkout.sessions.create.call_args.args[0]
        self.assertEqual(params["line_items"], [{"price_data": {
            "currency": "gbp", "product": "prod_listing_fixture", "unit_amount": 14525, "recurring": {"interval": "year"},
        }, "quantity": 1}])
        self.assertEqual(params["customer_email"], application.owner.email)
        self.assertEqual(urlsplit(params["cancel_url"]).path, checkout)
        self.assertFalse(published_placements(self.tour).exists())

        end = int((timezone.now() + timedelta(days=365)).timestamp())
        invoice_line = {"parent": {"subscription_item_details": {"subscription_item": "si_test", "proration": False}},
                        "period": {"end": end}}
        subscribed_price = {**self.stripe.prices.retrieve.return_value, "id": "price_inline_fixture", "unit_amount": 14525, "active": False}
        subscription = {
            "livemode": False, "metadata": params["metadata"], "customer": "cus_test",
            "status": "active", "latest_invoice": {"status": "paid", "lines": {"data": [invoice_line]}},
            "items": {"data": [{"id": "si_test", "price": subscribed_price, "quantity": 1, "current_period_end": end + 1000000}]},
        }
        self.stripe.subscriptions.retrieve.return_value = subscription
        completed = {"id": "cs_test_123", "livemode": False, "mode": "subscription", "subscription": "sub_test",
                     "metadata": params["metadata"], "client_reference_id": str(application.pk)}
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.signed_event("checkout.session.completed", completed).status_code, 204)
        self.assertEqual(mail.outbox[-1].subject, "Your EA600 business listing is live on the test preview")
        self.assertIn(f"{origin}/tours/ea600/#places-along-the-route", mail.outbox[-1].body)
        self.assertIn(f"{origin}/destinations/norwich/#destination-businesses", mail.outbox[-1].body)
        sent_count = len(mail.outbox)
        self.assertContains(Client().get(self.tour.get_absolute_url()), listing.name)
        self.assertRedirects(self.client.get(checkout), reverse("partners:dashboard"))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.signed_event("checkout.session.completed", completed).status_code, 204)
        self.assertEqual(len(mail.outbox), sent_count)
        application.refresh_from_db()
        paid_until = application.paid_until
        self.assertEqual(int(paid_until.timestamp()), end)
        self.assertEqual(application.checkout_amount_pence, 14525)

        invoice = {"parent": {"subscription_details": {"subscription": "sub_test"}}}
        subscription["status"] = "past_due"
        subscription["latest_invoice"]["status"] = "open"
        self.assertEqual(self.signed_event("invoice.payment_failed", invoice).status_code, 204)
        application.refresh_from_db()
        self.assertEqual(application.paid_until, paid_until)
        self.assertTrue(published_placements(self.tour).exists())
        with patch("partners.models.timezone.now", return_value=paid_until):
            self.assertFalse(published_placements(self.tour).exists())

        subscription["status"] = "active"
        subscription["latest_invoice"]["status"] = "paid"
        AdvertisePageSettings.objects.update(annual_price="160.00")
        invoice_line["period"]["end"] = end + 1000000
        subscription["cancel_at_period_end"] = True
        self.assertEqual(self.signed_event("invoice.paid", invoice).status_code, 204)
        self.assertTrue(published_placements(self.tour).exists())
        application.refresh_from_db()
        self.assertEqual(int(application.paid_until.timestamp()), end + 1000000)
        subscription["status"] = "canceled"
        self.assertEqual(self.signed_event("customer.subscription.deleted", {"id": "sub_test"}).status_code, 204)
        self.assertFalse(published_placements(self.tour).exists())
        self.assertEqual(self.signed_event("invoice.paid", invoice).status_code, 204)
        self.assertFalse(published_placements(self.tour).exists())

    @override_settings(PARTNER_PILOT_PREVIEW=True)
    def test_superuser_can_preview_payment_without_advertiser_email_or_stripe_key(self):
        application = self.apply_as_owner()
        another = PartnerApplication.objects.create(
            owner=application.owner,
            listing=BusinessListing.objects.create(name="Other business on this account"),
        )
        editor = Client(enforce_csrf_checks=True)
        sign_in_verified(editor, self.editor)
        edit_url = reverse("ea600_business_listings:edit", args=[application.listing_id])
        sandbox_url = reverse("ea600_business_listings:sandbox_payment", args=[application.listing_id])
        dashboard = reverse("partners:dashboard")
        checkout = reverse("partners:checkout", args=[application.pk])

        self.assertContains(editor.get(edit_url), "Advertiser payments")
        draft_payments = editor.get(sandbox_url)
        self.assertContains(draft_payments, "Publish this listing with a stop on a published route")
        self.assertNotContains(draft_payments, "Open My business listings")
        self.approve(application)
        with self.settings(EMAIL_HOST="", PARTNER_RESEND_API_KEY="", STRIPE_TEST_SECRET_KEY=""):
            self.assertContains(editor.get(edit_url), sandbox_url)
            self.assertContains(editor.get(sandbox_url), "Open My business listings")
            self.assertRedirects(editor.get(dashboard), reverse("partners:advertise"), fetch_redirect_response=False)
            self.assertEqual(editor.post(sandbox_url).status_code, 403)
            csrf = {"csrfmiddlewaretoken": editor.cookies["csrftoken"].value}
            self.assertRedirects(editor.post(sandbox_url, csrf), dashboard)
            page = editor.get(dashboard)
            self.assertContains(page, "Sandbox view for this listing")
            self.assertContains(page, "Choose a payment plan")
            self.assertContains(page, checkout)
            self.assertNotContains(page, another.listing.name)
            self.assertNotContains(page, "Apply for a listing")
            payment = editor.get(checkout)
            self.assertContains(payment, "Checkout is currently unavailable")
            self.assertContains(payment, "Choose monthly")
            self.assertContains(payment, "Choose annual")
            self.assertEqual(editor.get(reverse("partners:checkout", args=[another.pk])).status_code, 404)
            self.assertRedirects(editor.post(reverse("partners:sign_out"), csrf), edit_url)
            self.assertEqual(editor.get(checkout).status_code, 404)
            self.stripe.checkout.sessions.create.assert_not_called()

    @override_settings(PARTNER_PILOT_PREVIEW=True)
    def test_sandbox_scope_requires_verified_superuser_and_test_mode(self):
        application = self.apply_as_owner()
        self.approve(application)
        sandbox_url = reverse("ea600_business_listings:sandbox_payment", args=[application.listing_id])
        checkout = reverse("partners:checkout", args=[application.pk])
        staff = get_user_model().objects.create_user(username="sandbox-editor", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=("access_admin", "change_businesslisting")))
        editor = Client()
        sign_in_verified(editor, staff)
        self.assertContains(editor.get(reverse("ea600_business_listings:edit", args=[application.listing_id])), sandbox_url)
        payments = editor.get(sandbox_url)
        self.assertContains(payments, "The listing is approved for payment.")
        self.assertNotContains(payments, "Open My business listings")
        self.assertNotContains(payments, application.owner.email)
        self.assertEqual(editor.post(sandbox_url).status_code, 302)
        self.assertEqual(editor.get(checkout).status_code, 404)

        sign_in_verified(editor, self.editor)
        self.assertRedirects(editor.post(sandbox_url), reverse("partners:dashboard"))
        self.assertContains(editor.get(checkout), "Test checkout")
        with self.settings(PARTNER_APPLICATIONS_ENABLED=False):
            self.assertContains(editor.get(checkout), "Test checkout")
        with self.settings(PARTNER_BILLING_MODE="live"):
            self.assertEqual(editor.get(checkout).status_code, 404)
        with self.settings(PARTNER_PILOT_PREVIEW=False):
            self.assertEqual(editor.get(checkout).status_code, 404)
        with patch("partners.sandbox.timezone.now", return_value=timezone.now() + timedelta(minutes=21)):
            self.assertEqual(editor.get(checkout).status_code, 404)

        session = editor.session
        del session[DEVICE_ID_SESSION_KEY]
        session.save()
        self.assertEqual(editor.get(checkout).status_code, 404)

    @override_settings(PARTNER_PILOT_PREVIEW=True)
    def test_listing_created_in_wagtail_has_payment_status_without_an_advertiser(self):
        sign_in_verified(self.client, self.editor)
        self.assertEqual(self.client.post(reverse("ea600_business_listings:add"), {
            "name": "Complimentary Tea Room",
            "category": "food",
            "description": "Tea and cake",
            "address": "Norwich NR1",
            "link": "https://example.com/tea",
            "link_label": "website",
            "stops": [self.stop.pk],
            "action-publish": "1",
        }).status_code, 302)
        listing = BusinessListing.objects.get(name="Complimentary Tea Room")
        edit = reverse("ea600_business_listings:edit", args=[listing.pk])
        payments = reverse("ea600_business_listings:sandbox_payment", args=[listing.pk])
        self.assertContains(self.client.get(edit), payments)
        status = self.client.get(payments)
        self.assertContains(status, "This listing has no linked advertiser.")
        self.assertContains(status, reverse("ea600_advertising_enquiries:index"))
        self.assertNotContains(status, "Open My business listings")
        self.assertTrue(published_placements(self.tour).filter(listing=listing).exists())

    def test_open_checkout_is_requoted_when_an_owner_returns_after_price_change(self):
        application = self.apply_as_owner()
        self.approve(application)
        self.configure_price("month", 1200)
        checkout = reverse("partners:checkout", args=[application.pk])
        self.assertEqual(self.client.post(checkout, {"plan": "monthly"}).status_code, 302)
        self.assertEqual(self.stripe.checkout.sessions.create.call_args.args[0]["line_items"], [{"price": "price_month_fixture", "quantity": 1}])
        original_key = self.stripe.checkout.sessions.create.call_args.kwargs["options"]["idempotency_key"]

        AdvertisePageSettings.objects.update(monthly_price="17.50")
        self.stripe.checkout.sessions.retrieve.return_value = {"status": "open"}
        self.stripe.checkout.sessions.expire.return_value = {"status": "expired"}
        self.stripe.checkout.sessions.create.return_value = SimpleNamespace(id="cs_test_new", url="https://checkout.stripe.com/test-new")
        self.assertRedirects(self.client.post(checkout, {"plan": "monthly"}), "https://checkout.stripe.com/test-new", fetch_redirect_response=False)
        self.stripe.checkout.sessions.expire.assert_called_once_with("cs_test_123")
        call = self.stripe.checkout.sessions.create.call_args
        self.assertEqual(call.args[0]["line_items"][0]["price_data"]["unit_amount"], 1750)
        self.assertNotEqual(call.kwargs["options"]["idempotency_key"], original_key)
        application.refresh_from_db()
        self.assertEqual(application.checkout_amount_pence, 1750)

    def test_monthly_checkout_resumes_and_portal_requires_owner(self):
        application = self.apply_as_owner()
        self.approve(application)
        self.configure_price("month", 1200)
        checkout = reverse("partners:checkout", args=[application.pk])
        self.assertEqual(self.client.post(checkout, {"plan": "monthly"}).status_code, 302)
        self.stripe.prices.retrieve.assert_called_with("price_month_fixture")
        self.stripe.checkout.sessions.retrieve.return_value = {"status": "open", "url": "https://checkout.stripe.com/test"}
        self.assertEqual(self.client.post(checkout, {"plan": "monthly"}).status_code, 302)
        self.stripe.checkout.sessions.create.assert_called_once()

        PartnerApplication.objects.filter(pk=application.pk).update(stripe_customer_id="cus_test")
        other = PartnerAccount.objects.create(email="other@example.com")
        stranger = Client()
        session = stranger.session
        session["ea600_partner_owner"] = other.pk
        session.save()
        portal = reverse("partners:portal", args=[application.pk])
        self.assertEqual(stranger.post(portal).status_code, 404)
        self.stripe.billing_portal.sessions.create.return_value = SimpleNamespace(url="https://billing.stripe.com/test")
        self.assertRedirects(self.client.post(portal), "https://billing.stripe.com/test", fetch_redirect_response=False)
        self.assertEqual(self.stripe.billing_portal.sessions.create.call_args.args[0]["customer"], "cus_test")

    def test_rejects_unsigned_events_and_live_events(self):
        self.assertEqual(self.client.post(reverse("partners:webhook"), "{}", content_type="application/json").status_code, 400)
        self.assertEqual(self.signed_event("checkout.session.completed", {}, live=True).status_code, 400)
        self.assertFalse(BusinessListing.objects.filter(requires_subscription=True).exists())

    @override_settings(
        PARTNER_BILLING_MODE="live",
        STRIPE_LIVE_SECRET_KEY="sk_live_fixture", STRIPE_LIVE_WEBHOOK_SECRET="whsec_live_fixture",
        STRIPE_LIVE_MONTHLY_PRICE="price_live_month_fixture", STRIPE_LIVE_ANNUAL_PRICE="price_live_year_fixture",
    )
    def test_live_checkout_requires_a_live_payment_even_after_a_test_subscription(self):
        application = self.apply_as_owner()
        self.approve(application)
        checkout = reverse("partners:checkout", args=[application.pk])
        portal = reverse("partners:portal", args=[application.pk])
        PartnerApplication.objects.filter(pk=application.pk).update(
            checkout_id="cs_test_previous", checkout_plan="monthly", checkout_amount_pence=1200,
            stripe_customer_id="cus_test_previous", stripe_subscription_id="sub_test_previous",
            paid_until=timezone.now() + timedelta(days=30), billing_status="active",
        )
        self.assertFalse(published_placements(self.tour).exists())
        self.assertEqual(self.client.post(portal).status_code, 409)
        self.assertNotContains(self.client.get(checkout), "Test checkout")

        with self.settings(STRIPE_LIVE_SECRET_KEY="sk_test_fixture"):
            self.assertContains(self.client.get(checkout), "Checkout is currently unavailable")
            self.assertContains(self.client.get(checkout), 'value="monthly" disabled')
            self.assertEqual(self.client.post(checkout, {"plan": "monthly"}).status_code, 409)
        self.configure_price("month", 1200, live=True)
        self.stripe.checkout.sessions.create.return_value = SimpleNamespace(id="cs_live_123", url="https://checkout.stripe.com/live")
        self.assertRedirects(self.client.post(checkout, {"plan": "monthly"}), "https://checkout.stripe.com/live", fetch_redirect_response=False)
        self.stripe.prices.retrieve.assert_called_once_with("price_live_month_fixture")
        self.stripe.checkout.sessions.retrieve.assert_not_called()
        params = self.stripe.checkout.sessions.create.call_args.args[0]
        self.assertNotIn("customer", params)
        application.refresh_from_db()
        self.assertEqual(application.billing_mode, PartnerApplication.BillingMode.LIVE)
        self.assertIsNone(application.paid_until)

        end = int((timezone.now() + timedelta(days=30)).timestamp())
        invoice = {
            "status": "open", "parent": {"subscription_details": {"subscription": "sub_live"}},
            "lines": {"data": [{
                "parent": {"subscription_item_details": {"subscription_item": "si_live", "proration": False}},
                "period": {"end": end},
            }]},
        }
        self.stripe.subscriptions.retrieve.return_value = {
            "livemode": True, "metadata": params["metadata"], "customer": "cus_live",
            "status": "active", "latest_invoice": invoice, "items": {"data": [{
                "id": "si_live", "price": self.stripe.prices.retrieve.return_value, "quantity": 1,
            }]},
        }
        completed = {
            "id": "cs_live_123", "livemode": True, "mode": "subscription", "subscription": "sub_live",
            "metadata": params["metadata"], "client_reference_id": str(application.pk),
        }
        secret = b"whsec_live_fixture"
        self.assertEqual(self.signed_event("checkout.session.completed", completed, live=True).status_code, 400)
        self.assertEqual(self.signed_event("checkout.session.completed", completed, secret=secret).status_code, 400)
        self.assertEqual(self.signed_event("checkout.session.completed", completed, live=True, secret=secret).status_code, 204)
        self.assertFalse(published_placements(self.tour).exists())
        invoice["status"] = "paid"
        self.assertEqual(self.signed_event("invoice.paid", invoice, live=True, secret=secret).status_code, 204)
        self.assertContains(Client().get(self.tour.get_absolute_url()), application.listing.name)
        with self.settings(PARTNER_BILLING_MODE="test"):
            self.assertFalse(published_placements(self.tour).exists())
            self.assertEqual(self.client.post(portal).status_code, 409)

    @override_settings(
        PARTNER_RESEND_API_KEY="re_test_fixture", DEFAULT_FROM_EMAIL="EA600 <partners@example.com>",
        EA600_PUBLIC_DOMAIN="preview.example.com",
    )
    @patch("partners.mail.urlopen")
    def test_sign_in_link_can_be_sent_using_https_email(self, urlopen):
        PartnerAccount.objects.create(email="owner@example.com")
        self.assertContains(self.client.post(reverse("partners:advertise"), {"email": "owner@example.com"}), "Check your inbox")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test_fixture")
        message = json.loads(request.data)
        self.assertEqual(message["to"], ["owner@example.com"])
        self.assertIn("https://preview.example.com/advertise/access/", message["text"])

    def test_confirmation_reuses_an_account_and_preserves_the_uploaded_photo(self):
        owner = PartnerAccount.objects.create(email="owner@example.com")
        image_data = BytesIO()
        Image.new("RGB", (24, 16), "green").save(image_data, "PNG")
        photo = SimpleUploadedFile("shop.png", image_data.getvalue(), content_type="image/png")
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            application = self.apply_as_owner(photo_upload=photo)
            self.assertEqual(application.owner, owner)
            self.assertEqual(PartnerAccount.objects.count(), 1)
            self.assertTrue(application.listing.photo.image.storage.exists(application.listing.photo.image.name))
            edit_url = reverse("partners:edit_listing", args=[application.pk])
            self.assertEqual(Client().get(edit_url).status_code, 404)
            self.assertContains(self.client.get(edit_url), "Save changes for review")
            self.assertRedirects(self.client.post(edit_url, {
                "description": "New menu", "link": "https://example.com/menu", "link_label": "website",
                "revision": application.listing.latest_revision_id,
            }), reverse("partners:dashboard") + "?listing=updated")
            application.listing.refresh_from_db()
            self.assertEqual(application.listing.description, "Tea and scones")
            self.assertEqual(application.listing.get_latest_revision_as_object().description, "New menu")

    def test_unverified_application_does_not_create_an_account_or_draft(self):
        self.assertContains(self.client.post(reverse("partners:apply"), {
            "email": "new@example.com", "name": "New listing", "category": "food",
            "description": "A new cafe", "address": "Norwich", "stop": self.stop.pk,
            "link": "https://example.com", "link_label": "website",
        }), "Check your inbox")
        self.assertFalse(PartnerAccount.objects.exists())
        self.assertFalse(BusinessListing.objects.exists())
        self.assertTrue(PendingPartnerApplication.objects.exists())
