from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .builder_views import tour_version
from .models import Destination, HomeContent, ItineraryDay, Photo, Tour, TourStop
from .test_support import sign_in_verified


class TourBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(username="builder-editor")

    def setUp(self):
        sign_in_verified(self.client, self.editor)

    def test_preview_then_save_and_publish_a_new_tour(self):
        url = reverse("builder_new")
        self.assertContains(self.client.get(url), "Add stop")
        photo = Photo.objects.get(bundled_path="assets/images/norwich.webp")
        destination = Destination.objects.create(
            title="Wroxham", slug="wroxham", region="Norfolk Broads", description="Riverside village.", photo=photo,
        )
        data = {
            "title": "Broads Loop", "slug": "broads-loop", "summary": "A weekend by the water.",
            "region": "Norfolk Broads", "distance_miles": 90, "duration_days": 2,
            "position": 0, "cover": photo.pk, "gallery": [photo.pk],
            "stops-TOTAL_FORMS": 2, "stops-INITIAL_FORMS": 0,
            "stops-0-title": "Wroxham", "stops-0-destination": destination.pk, "stops-0-ORDER": 2,
            "stops-1-title": "Horning", "stops-1-region": "Norfolk", "stops-1-ORDER": 1,
            "stops-1-description": "Visit the village on the River Bure.",
            "days-TOTAL_FORMS": 1, "days-INITIAL_FORMS": 0,
            "days-0-number": 1, "days-0-title": "The Broads", "days-0-photo": photo.pk,
            "days-0-description": "Follow the river from Horning to Wroxham.",
        }

        preview = self.client.post(url, {**data, "action": "preview"})
        self.assertContains(preview, "Preview · Close this tab")
        self.assertContains(preview, photo.url)
        self.assertContains(preview, data["days-0-description"])
        self.assertLess(preview.content.index(b"Horning"), preview.content.index(b"Wroxham"))
        self.assertFalse(Tour.objects.filter(slug="broads-loop").exists())
        self.assertFalse(Destination.objects.filter(slug="horning").exists())

        result = self.client.post(url, {**data, "action": "draft"})
        self.assertEqual(result.status_code, 302)
        tour = Tour.objects.get(slug="broads-loop")
        self.assertFalse(tour.is_published)
        self.assertFalse(Destination.objects.filter(slug="horning").exists())
        self.assertEqual(list(tour.stops.values_list("title", flat=True)), ["Horning", "Wroxham"])
        self.assertEqual(tour.days.get().photo, photo)
        self.assertEqual(self.client.get(tour.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("tour_list")), tour.title)

        edit = reverse("builder_edit", args=[tour.pk])
        data.update({
            "action": "publish", "version": tour_version(tour),
            "stops-INITIAL_FORMS": 2, "days-INITIAL_FORMS": 1, "days-0-id": tour.days.get().pk,
        })
        for index, stop in enumerate(tour.stops.all()):
            data.update({
                f"stops-{index}-id": stop.pk, f"stops-{index}-title": stop.title,
                f"stops-{index}-region": stop.region, f"stops-{index}-description": stop.description,
                f"stops-{index}-destination": stop.destination_id or "", f"stops-{index}-ORDER": index + 1,
            })
        self.assertRedirects(self.client.post(edit, data), edit, fetch_redirect_response=False)
        self.assertContains(self.client.get(tour.get_absolute_url()), "Broads Loop")
        self.assertContains(self.client.get(tour.get_absolute_url()), data["days-0-description"])
        self.assertContains(self.client.get(tour.get_absolute_url()), f'href="{destination.get_absolute_url()}"')
        horning = tour.stops.get(title="Horning").destination
        self.assertEqual(horning.region, "Norfolk")
        self.assertEqual(horning.description, "Visit the village on the River Bure.")
        self.assertContains(self.client.get(tour.get_absolute_url()), f'href="{horning.get_absolute_url()}"')
        catalogue = self.client.get(reverse("tour_list"))
        self.assertContains(catalogue, "Broads Loop")
        self.assertContains(catalogue, "Norfolk Broads")
        self.assertContains(catalogue, "90 miles")
        self.assertContains(catalogue, "2 days")
        home = self.client.get(reverse("home"))
        self.assertContains(home, 'href="/tours/broads-loop/"')
        self.assertEqual(home.context["tour"].slug, "ea600")
        self.assertLess(home.content.index(b'id="tours"'), home.content.index(b'id="routes"'))

    def test_swapping_day_numbers_preserves_both_rows(self):
        tour = Tour.objects.create(title="Two days", slug="two-days", summary="Two days", is_published=True)
        first = ItineraryDay.objects.create(tour=tour, number=1, title="First")
        second = ItineraryDay.objects.create(tour=tour, number=2, title="Second")
        url = reverse("builder_edit", args=[tour.pk])
        data = {
            "title": tour.title, "slug": tour.slug, "summary": tour.summary, "position": tour.position,
            "action": "publish", "version": tour_version(tour),
            "stops-TOTAL_FORMS": 0, "stops-INITIAL_FORMS": 0,
            "days-TOTAL_FORMS": 2, "days-INITIAL_FORMS": 2,
            "days-0-id": first.pk, "days-0-number": 2, "days-0-title": first.title,
            "days-1-id": second.pk, "days-1-number": 1, "days-1-title": second.title,
        }
        result = self.client.post(url, data)
        self.assertEqual(result.status_code, 302, result.context and result.context["days"].errors)
        self.assertEqual(list(tour.days.values_list("pk", flat=True)), [second.pk, first.pk])
        self.assertTrue(Tour.objects.get(pk=tour.pk).is_published)

    def test_stale_editor_cannot_overwrite_a_saved_tour(self):
        tour = Tour.objects.create(title="Saved", slug="saved", summary="A saved tour.")
        version = tour_version(tour)
        TourStop.objects.create(tour=tour, title="Stop added by another editor")
        result = self.client.post(reverse("builder_edit", args=[tour.pk]), {
            "action": "draft", "version": version, "title": "Stale draft", "slug": tour.slug,
            "summary": tour.summary, "position": tour.position,
            "stops-TOTAL_FORMS": 0, "stops-INITIAL_FORMS": 0,
            "days-TOTAL_FORMS": 0, "days-INITIAL_FORMS": 0,
        })
        self.assertContains(result, "This tour was edited elsewhere", status_code=409)
        tour.refresh_from_db()
        self.assertEqual(tour.title, "Saved")
        self.assertEqual(tour.stops.count(), 1)

    def test_unpublish_featured_tour_keeps_a_draft_and_homepage_falls_back(self):
        home = HomeContent.objects.get()
        tour = home.featured_tour
        fallback = Tour.objects.create(
            title="Fallback", slug="fallback", summary="Another published tour", is_published=True,
        )
        url = reverse("builder_unpublish", args=[tour.pk])
        self.assertContains(self.client.get(url), "It will remain here as a draft")
        self.assertEqual(self.client.get(tour.get_absolute_url()).status_code, 200)
        edit = reverse("builder_edit", args=[tour.pk])
        self.assertRedirects(self.client.post(url, {"version": tour_version(tour)}), edit)
        tour.refresh_from_db()
        self.assertFalse(tour.is_published)
        self.assertTrue(tour.stops.exists())
        self.assertEqual(self.client.get(tour.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get("/").context["tour"], fallback)

    def test_delete_checks_permissions_and_confirmation_then_preserves_photos(self):
        tour = HomeContent.objects.get().featured_tour
        photo = tour.cover
        url = reverse("builder_delete", args=[tour.pk])
        editor = get_user_model().objects.create_user(username="changes-only", is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename="change_tour"))
        sign_in_verified(self.client, editor)
        self.assertEqual(self.client.post(url, {"version": tour_version(tour)}).status_code, 403)

        sign_in_verified(self.client, self.editor)
        self.assertContains(self.client.get(url), "This permanently deletes the tour")
        self.assertTrue(Tour.objects.filter(pk=tour.pk).exists())
        self.assertEqual(self.client.post(url, {"version": "stale"}).status_code, 409)
        self.assertTrue(Tour.objects.filter(pk=tour.pk).exists())
        self.assertRedirects(self.client.post(url, {
            "version": tour_version(tour),
        }), reverse("builder_index"))
        self.assertFalse(Tour.objects.filter(pk=tour.pk).exists())
        self.assertFalse(TourStop.objects.filter(tour=tour).exists())
        self.assertTrue(Photo.objects.filter(pk=photo.pk).exists())
        self.assertIsNone(HomeContent.objects.get().featured_tour)
        self.assertEqual(self.client.get(tour.get_absolute_url()).status_code, 404)

    def test_photo_upload_uses_the_shared_library_and_builder_requires_permission(self):
        protected = reverse("builder_photos")
        self.client.logout()
        self.assertEqual(self.client.get(protected).status_code, 302)
        staff = get_user_model().objects.create_user(username="read-only-staff", is_staff=True)
        sign_in_verified(self.client, staff)
        self.assertEqual(self.client.get(protected).status_code, 403)

        sign_in_verified(self.client, self.editor)
        png = BytesIO()
        Image.new("RGB", (8, 8), "green").save(png, "PNG")
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(protected, {
                "title": "Builder upload", "alt_text": "Green test image",
                "image": SimpleUploadedFile("builder.png", png.getvalue(), content_type="image/png"),
            })
            self.assertEqual(response.status_code, 201)
            photo = Photo.objects.get(title="Builder upload")
            self.assertEqual(response.json()["photo"]["url"], photo.url)
            self.assertEqual(self.client.get(protected, {"q": "Builder upload"}).json()["photos"][0]["id"], photo.pk)
            self.assertEqual(self.client.get(photo.url).status_code, 200)
