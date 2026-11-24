from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Destination, HomeContent, Photo, Tour


class ContentTests(TestCase):
    def test_wagtail_destination_editor_updates_the_homepage_card(self):
        editor = get_user_model().objects.create_superuser(username="destination-editor")
        self.client.force_login(editor)
        destination = Destination.objects.get(title="Norwich")
        listing = reverse("ea600_destinations:list")
        edit = reverse("ea600_destinations:edit", args=[destination.pk])

        self.assertContains(self.client.get("/cms/"), listing)
        self.assertContains(self.client.get(listing, {"q": "Norwich"}), destination.title)
        self.assertContains(self.client.get(edit), "Choose another photo")
        text = "A new introduction to Norwich."
        response = self.client.post(edit, {
            "title": destination.title,
            "region": destination.region,
            "description": text,
            "photo": destination.photo_id,
            "link": destination.link,
            "position": destination.position,
        })
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("home")), text)

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
        Tour.objects.bulk_create([
            Tour(title=f"Tour {number}", slug=f"test-{number}", summary="Tour description", is_published=True)
            for number in range(13)
        ])
        draft = Tour.objects.create(title="Private draft", slug="private", summary="Still in progress")
        first_page = self.client.get(reverse("tour_list"))
        second_page = self.client.get(reverse("tour_list"), {"page": 2})
        self.assertEqual(first_page.context["page"].paginator.count, 14)
        self.assertEqual(len(second_page.context["page"].object_list), 2)
        self.assertNotContains(first_page, draft.title)
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)

    def test_editor_can_upload_and_publish_a_tour_with_an_itinerary(self):
        editor = get_user_model().objects.create_superuser(username="preview-editor")
        self.client.force_login(editor)
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
