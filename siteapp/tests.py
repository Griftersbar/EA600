from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from partners.models import BusinessListing, PartnerAccount, PartnerApplication, RoutePlacement

from .models import Destination, HomeContent, Photo, Tour
from .test_support import sign_in_verified


class ContentTests(TestCase):
    def test_public_footer_reuses_contact_details_from_site_settings(self):
        HomeContent.objects.update(contact_email="route-team@example.test")
        for path in ("/", "/tours/", "/tours/ea600-14-day/", "/advertise/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, '<footer class="site-footer" id="contact">')
                self.assertContains(response, 'href="mailto:route-team@example.test"')
                self.assertContains(response, '<nav class="site-footer__nav" aria-label="Footer">')

    def test_public_navigation_marks_the_current_page_or_section(self):
        for path, href, label, current in (
            ("/", "#top", "Home", "page"),
            ("/tours/", "/tours/", "Explore routes", "page"),
            ("/tours/ea600-14-day/", "/tours/", "Explore routes", "location"),
            ("/advertise/", "/advertise/", "Advertise", "page"),
        ):
            with self.subTest(path=path):
                extra = ' data-nav-sections="top"' if path == "/" else ""
                self.assertContains(
                    self.client.get(path),
                    f'<a class="nav__link" href="{href}"{extra} aria-current="{current}">{label}</a>',
                    html=True,
                )

    def test_wagtail_destination_editor_updates_the_homepage_card_and_detail(self):
        editor = get_user_model().objects.create_superuser(username="destination-editor")
        sign_in_verified(self.client, editor)
        destination = Destination.objects.get(title="Norwich")
        listing = reverse("ea600_destinations:list")
        edit = reverse("ea600_destinations:edit", args=[destination.pk])

        self.assertContains(self.client.get("/cms/"), listing)
        self.assertContains(self.client.get(listing, {"q": "Norwich"}), destination.title)
        self.assertContains(self.client.get(edit), "Choose another photo")
        gallery_photo = Photo.objects.exclude(pk=destination.photo_id).get(bundled_path="assets/images/intro-stack-1.webp")
        text = "A new introduction to Norwich."
        response = self.client.post(edit, {
            "title": destination.title,
            "slug": destination.slug,
            "region": destination.region,
            "description": text,
            "photo": destination.photo_id,
            "link": "https://example.test/norwich",
            "position": destination.position,
            "gallery-TOTAL_FORMS": 1,
            "gallery-INITIAL_FORMS": 0,
            "gallery-0-photo": gallery_photo.pk,
            "gallery-0-ORDER": 0,
        })
        self.assertEqual(response.status_code, 302)
        home = self.client.get(reverse("home"))
        self.assertContains(home, text)
        self.assertContains(home, f'href="{destination.get_absolute_url()}"')
        detail = self.client.get(destination.get_absolute_url())
        self.assertContains(detail, text)
        self.assertContains(detail, destination.photo.url)
        self.assertContains(detail, gallery_photo.url)
        self.assertContains(detail, 'href="https://example.test/norwich"')

    def test_existing_route_stops_link_to_the_same_destination_across_routes(self):
        destination = Destination.objects.get(slug="cromer")
        for slug in ("ea600", "ea600-3-day", "ea600-14-day"):
            tour = Tour.objects.get(slug=slug)
            self.assertEqual(tour.stops.get(title="Cromer").destination, destination)
            self.assertContains(self.client.get(tour.get_absolute_url()), f'href="{destination.get_absolute_url()}"')
            self.assertContains(self.client.get(destination.get_absolute_url()), f'href="{tour.get_absolute_url()}"')
        self.assertEqual(self.client.get("/destinations/unknown/").status_code, 404)

    @override_settings(PARTNER_BILLING_MODE="live", PARTNER_PILOT_PREVIEW=False)
    def test_destination_only_lists_eligible_local_advertisers_once(self):
        destination = Destination.objects.get(slug="norwich")
        stops = list(destination.route_stops.filter(tour__is_published=True))
        draft = Tour.objects.create(title="Draft Norwich route", slug="draft-norwich", summary="Private")
        draft_stop = draft.stops.create(title="Norwich", destination=destination)
        elsewhere = Tour.objects.get(slug="ea600").stops.get(title="Cromer")
        owner = PartnerAccount.objects.create(email="norwich-business@example.test")

        def listing(name, stop, **settings):
            business = BusinessListing.objects.create(name=name, category="food", live=True, **settings)
            RoutePlacement.objects.create(listing=business, stop=stop)
            return business

        paid = listing("Norwich paid tea room", stops[0], requires_subscription=True)
        PartnerApplication.objects.create(
            listing=paid, owner=owner, billing_mode="live", billing_status="active",
            paid_until=timezone.now() + timedelta(days=30),
        )
        RoutePlacement.objects.create(listing=paid, stop=stops[1])
        unpaid = listing("Norwich awaiting payment", stops[0], requires_subscription=True)
        draft_route_ad = listing("Private route business", draft_stop)
        other_town_ad = listing("Cromer tea room", elsewhere)
        pilot_ad = listing("Hidden pilot tea room", stops[0], demo_key="hidden-pilot")
        unpublished = listing("Norwich unpublished tea room", stops[0])
        BusinessListing.objects.filter(pk=unpublished.pk).update(live=False)

        page = self.client.get(destination.get_absolute_url())
        self.assertContains(page, paid.name, count=1)
        placement = paid.placements.order_by("pk").first()
        self.assertContains(page, reverse("partners:listing_click", args=[placement.pk, "website"]))
        for hidden in (unpaid, draft_route_ad, other_town_ad, pilot_ad, unpublished):
            self.assertNotContains(page, hidden.name)
        self.assertNotContains(page, draft.get_absolute_url())
        PartnerApplication.objects.filter(listing=paid).update(paid_until=timezone.now() - timedelta(days=1))
        self.assertNotContains(self.client.get(destination.get_absolute_url()), paid.name)

    def test_existing_route_and_homepage_are_loaded_from_editable_content(self):
        tour = Tour.objects.get(slug="ea600")
        self.assertTrue(tour.is_published)
        self.assertEqual(tour.stops.count(), 12)
        self.assertContains(self.client.get(tour.get_absolute_url()), "Fens &amp; Cathedrals")

        homepage = HomeContent.objects.get()
        homepage.hero_title = "Discover East Anglia"
        homepage.save(update_fields=["hero_title"])
        self.assertContains(self.client.get(reverse("home")), homepage.hero_title)

    def test_catalog_paginates_published_tours_and_hides_drafts(self):
        initial_count = Tour.objects.filter(is_published=True).count()
        Tour.objects.bulk_create([
            Tour(title=f"Tour {number}", slug=f"test-{number}", summary="Tour description", is_published=True)
            for number in range(13)
        ])
        draft = Tour.objects.create(title="Private draft", slug="private", summary="Still in progress")
        first_page = self.client.get(reverse("tour_list"))
        second_page = self.client.get(reverse("tour_list"), {"page": 2})
        self.assertEqual(first_page.context["page"].paginator.count, initial_count + 13)
        self.assertEqual(len(second_page.context["page"].object_list), initial_count + 1)
        self.assertNotContains(first_page, draft.title)
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)

    def test_imported_ea600_itineraries_are_available_in_the_planner_and_wagtail(self):
        home = self.client.get(reverse("home"))
        self.assertEqual(home.context["tour"].slug, "ea600")
        catalogue = self.client.get(reverse("tour_list"))
        editor = get_user_model().objects.create_superuser(username="itinerary-editor")
        sign_in_verified(self.client, editor)
        self.assertContains(self.client.get("/cms/"), reverse("builder_index"))
        builder = self.client.get(reverse("builder_index"))
        chooser = self.client.get(reverse("guide-tour-chooser:choose"))

        for length, miles, final_day in ((3, 600, "Suffolk and Essex return"), (14, 665, "Cambridge finale")):
            with self.subTest(days=length):
                tour = Tour.objects.get(slug=f"ea600-{length}-day")
                self.assertIn((tour.slug, tour.title), home.context["route_choices"])
                self.assertContains(catalogue, tour.get_absolute_url())
                self.assertContains(builder, tour.title)
                self.assertContains(chooser, tour.title)
                selected = self.client.get(reverse("home"), {"route": tour.slug})
                self.assertEqual(selected.context["tour"], tour)
                map_data = selected.context["geographic_map"]
                self.assertEqual(map_data["track"], [])
                self.assertEqual(map_data["stops"][0]["title"], "Cambridge")
                self.assertEqual(len(map_data["stops"]), tour.stops.count())
                public = self.client.get(tour.get_absolute_url())
                self.assertContains(public, f'id="day-{length}"')
                self.assertContains(public, final_day)
                self.assertEqual(tour.distance_miles, miles)
                self.assertEqual(list(tour.days.values_list("number", flat=True)), list(range(1, length + 1)))
                self.assertContains(self.client.get(reverse("builder_edit", args=[tour.pk])), final_day)

    def test_homepage_picker_switches_route_copy_map_stops_and_itinerary(self):
        homepage = HomeContent.objects.get()
        track = [[[51.64, -2.67], [51.91, -2.59]]]
        tour = Tour.objects.create(
            title="Wye Valley 150", slug="wye-valley-150", region="Wye Valley",
            summary="Follow the river from Tintern to Ross-on-Wye.", distance_miles=150,
            route_track=track, is_published=True, position=20,
        )
        stop = tour.stops.create(title="Tintern Abbey", latitude="51.64", longitude="-2.67")
        day = tour.days.create(number=1, title="A day beside the Wye")
        Tour.objects.bulk_create([
            Tour(title=f"Tour {number}", slug=f"route-{number}", is_published=True)
            for number in range(3)
        ])

        default = self.client.get(reverse("home"))
        self.assertEqual(default.context["tour"], homepage.featured_tour)
        self.assertContains(default, '<option value="ea600" selected>EA600 East Anglia Road Trip</option>', html=True)
        self.assertContains(default, homepage.itinerary_title)
        self.assertContains(default, "route-map-frame__img")
        self.assertNotIn(tour, default.context["tours"])
        self.assertIn((tour.slug, tour.title), default.context["route_choices"])
        featured = self.client.get(reverse("home"), {"route": homepage.featured_tour.slug})
        self.assertContains(featured, homepage.itinerary_title)

        selected = self.client.get(reverse("home"), {"route": tour.slug})
        self.assertContains(selected, '<option value="wye-valley-150" selected>Wye Valley 150</option>', html=True)
        self.assertContains(selected, '<h2 class="heading-section heading-section--center" id="routes-title">Wye Valley 150</h2>', html=True)
        self.assertContains(selected, tour.summary)
        self.assertContains(selected, "data-geographic-route")
        self.assertEqual(selected.context["geographic_map"], {
            "track": track, "stops": [{"number": 1, "title": stop.title, "position": [51.64, -2.67]}],
        })
        self.assertEqual(selected.context["stops"], [stop])
        self.assertEqual(list(selected.context["days"]), [day])
        self.assertContains(selected, day.title)
        self.assertContains(selected, f'href="{tour.get_absolute_url()}#itinerary"')
        self.assertNotContains(selected, homepage.itinerary_title)
        self.assertNotContains(selected, "route-map-frame__img")

    def test_homepage_picker_falls_back_when_a_route_is_unavailable(self):
        draft = Tour.objects.create(title="Private draft", slug="private-route", summary="Unpublished route")
        homepage = HomeContent.objects.get()
        featured = Tour.objects.create(title="Coast route", slug="coast-route", is_published=True)
        homepage.featured_tour = featured
        homepage.save(update_fields=["featured_tour"])

        for slug in (draft.slug, "missing-route"):
            with self.subTest(slug=slug):
                response = self.client.get(reverse("home"), {"route": slug})
                self.assertEqual(response.context["tour"], featured)
                self.assertNotContains(response, draft.title)

        Tour.objects.update(is_published=False)
        empty = self.client.get(reverse("home"), {"route": featured.slug})
        self.assertIsNone(empty.context["tour"])
        self.assertNotContains(empty, 'name="route"')

    def test_editor_can_upload_and_publish_a_tour_with_an_itinerary(self):
        editor = get_user_model().objects.create_superuser(username="preview-editor")
        sign_in_verified(self.client, editor)
        png = BytesIO()
        Image.new("RGB", (8, 8), "green").save(png, "PNG")
        photo_admin = reverse("admin:siteapp_photo_add")

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            photo_response = self.client.post(photo_admin, {
                "title": "A new tour photo",
                "alt_text": "An East Anglian landscape",
                "image": SimpleUploadedFile("tour.png", png.getvalue(), content_type="image/png"),
            })
            self.assertEqual(photo_response.status_code, 302, photo_response.context and photo_response.context["adminform"].form.errors)
            photo = Photo.objects.get(title="A new tour photo")

            tour_response = self.client.post(reverse("admin:siteapp_tour_add"), {
                "title": "Coastal Escape",
                "slug": "coastal-escape",
                "summary": "A day beside the sea.",
                "position": 1,
                "cover": photo.pk,
                "gallery": [photo.pk],
                "is_published": "on",
                "stops-TOTAL_FORMS": 1,
                "stops-INITIAL_FORMS": 0,
                "stops-0-title": "Southwold Pier",
                "stops-0-position": 0,
                "days-TOTAL_FORMS": 1,
                "days-INITIAL_FORMS": 0,
                "days-0-number": 1,
                "days-0-title": "A walk on the coast",
                "days-0-highlights": "Walk the pier\nVisit the lighthouse",
                "days-0-photo": photo.pk,
            })
            self.assertEqual(tour_response.status_code, 302, tour_response.context and tour_response.context["errors"])
            tour = Tour.objects.get(slug="coastal-escape")
            detail = self.client.get(tour.get_absolute_url())
            self.assertContains(detail, "Southwold Pier")
            self.assertContains(detail, "Visit the lighthouse")
            self.assertContains(detail, photo.url)
            self.assertContains(self.client.get(reverse("tour_list")), tour.title)

            image = self.client.get(photo.url)
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.headers["Content-Type"], "image/png")
            self.assertEqual(b"".join(image.streaming_content), png.getvalue())
            self.assertEqual(self.client.get("/media/db.sqlite3").status_code, 404)
