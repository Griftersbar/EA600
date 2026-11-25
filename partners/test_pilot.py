from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from siteapp.models import Tour
from siteapp.test_support import sign_in_verified

from .activity import PILOT_TIME_ZONE
from .models import BusinessListing, ListingClick, PartnerAccount, PartnerApplication, RoutePlacement
from .views import OWNER_SESSION


class PilotActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tour = Tour.objects.get(slug="ea600")
        cls.stop = cls.tour.stops.get(title="Norwich")

    def listing(self, **fields):
        defaults = {
            "name": "A listing for review", "address": "Norwich, NR1", "description": "A test listing.",
            "category": "food", "link": "https://example.com/book", "live": True,
        }
        listing = BusinessListing.objects.create(**(defaults | fields))
        return RoutePlacement.objects.create(listing=listing, stop=self.stop)

    def test_real_links_count_clicks_and_redirect_only_to_listing_destinations(self):
        placement = self.listing(link_label="booking")
        booking = reverse("partners:listing_click", args=[placement.pk, "booking"])
        direction = reverse("partners:listing_click", args=[placement.pk, "directions"])
        public = self.tour.get_absolute_url()
        self.assertContains(self.client.get(public), f'href="{booking}"')
        self.assertEqual(self.client.head(booking).status_code, 302)
        self.assertEqual(self.client.get(booking, headers={"Sec-Purpose": "prefetch"}).status_code, 302)
        self.assertFalse(ListingClick.objects.exists())
        for _ in range(2):
            self.assertRedirects(self.client.get(booking, {"next": "https://example.org"}), placement.listing.link,
                                 fetch_redirect_response=False)
        self.assertRedirects(self.client.get(direction), placement.listing.directions_url, fetch_redirect_response=False)
        self.assertEqual(dict(ListingClick.objects.values_list("action", "count")), {"booking": 2, "directions": 1})
        self.assertEqual(self.client.get(reverse("partners:listing_click", args=[placement.pk, "website"])).status_code, 404)
        self.tour.is_published = False
        self.tour.save(update_fields=["is_published"])
        self.assertEqual(self.client.get(direction).status_code, 404)

    def test_unpaid_or_unpublished_listing_does_not_redirect_or_count(self):
        placement = self.listing(requires_subscription=True)
        url = reverse("partners:listing_click", args=[placement.pk, "website"])
        self.assertEqual(self.client.get(url).status_code, 404)
        account = PartnerAccount.objects.create(email="owner@example.test")
        PartnerApplication.objects.create(owner=account, listing=placement.listing, billing_status="active",
                                          paid_until=timezone.now() + timedelta(days=1))
        self.assertEqual(self.client.get(url).status_code, 302)
        placement.listing.live = False
        placement.listing.save(update_fields=["live"])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(ListingClick.objects.get().count, 1)

    def test_owner_only_sees_their_30_day_activity_and_staff_sees_listing_totals(self):
        own = self.listing(name="Own listing")
        other = self.listing(name="Another owner's listing")
        account = PartnerAccount.objects.create(email="owner@example.test")
        stranger = PartnerAccount.objects.create(email="other@example.test")
        PartnerApplication.objects.create(owner=account, listing=own.listing)
        PartnerApplication.objects.create(owner=stranger, listing=other.listing)
        today = timezone.localdate(timezone=PILOT_TIME_ZONE)
        ListingClick.objects.bulk_create([
            ListingClick(listing=own.listing, day=today, action="website", count=2),
            ListingClick(listing=own.listing, day=today - timedelta(days=29), action="website", count=1),
            ListingClick(listing=own.listing, day=today - timedelta(days=30), action="website", count=21),
            ListingClick(listing=other.listing, day=today, action="website", count=11),
        ])
        dashboard = reverse("partners:dashboard")
        self.assertRedirects(self.client.get(dashboard), reverse("partners:advertise"))
        session = self.client.session
        session[OWNER_SESSION] = account.pk
        session.save()
        page = self.client.get(dashboard)
        self.assertContains(page, '<dd data-clicks="website">3</dd>', html=True)
        self.assertNotContains(page, other.listing.name)

        editor = Client()
        sign_in_verified(editor, get_user_model().objects.create_superuser(username="pilot-reviewer"))
        index = reverse("ea600_business_listings:list")
        self.assertEqual(self.client.get(index).status_code, 302)
        report = editor.get(index)
        self.assertContains(report, "Website clicks · 30 days")
        self.assertEqual({row.name: row.website_clicks for row in report.context["object_list"]},
                         {own.listing.name: 3, other.listing.name: 11})

    def test_demo_seed_is_repeatable_and_does_not_publish_outside_preview(self):
        with override_settings(PARTNER_PILOT_PREVIEW=False):
            with self.assertRaises(CommandError):
                call_command("seed_partner_pilot", stdout=StringIO())
        with override_settings(PARTNER_PILOT_PREVIEW=True):
            call_command("seed_partner_pilot", stdout=StringIO())
            call_command("seed_partner_pilot", stdout=StringIO())
            self.assertEqual(BusinessListing.objects.filter(demo_key__isnull=False).count(), 10)
            self.assertContains(self.client.get(self.tour.get_absolute_url()), "Test business</span>", count=10)
            pilot = reverse("partners:pilot")
            self.assertContains(self.client.get(pilot), "Clicks in the last 30 days", count=10)
            placement = RoutePlacement.objects.get(listing__demo_key="mile-marker")
            direction = reverse("partners:listing_click", args=[placement.pk, "directions"])
            click = self.client.get(direction)
            self.assertRedirects(click, pilot + f"#listing-{placement.listing_id}")
            self.assertContains(self.client.get(pilot), '<dd data-clicks="directions">1</dd>', count=1, html=True)

            placement.listing.unpublish()
            call_command("seed_partner_pilot", stdout=StringIO())
            self.assertEqual(self.client.get(direction).status_code, 404)
            self.assertEqual(ListingClick.objects.get().count, 1)

        with override_settings(PARTNER_PILOT_PREVIEW=False):
            self.assertNotContains(self.client.get(self.tour.get_absolute_url()), "Test business</span>")
            self.assertEqual(self.client.get(pilot).status_code, 404)
            self.assertEqual(self.client.get(reverse("partners:listing_click", args=[
                RoutePlacement.objects.get(listing__demo_key="reed-and-linen").pk, "booking",
            ])).status_code, 404)
