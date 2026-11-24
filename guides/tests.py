from io import BytesIO, StringIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from siteapp.builder_views import tour_version
from siteapp.models import Photo, Tour

from .models import DestinationGuidePage, GuideIndexPage


class GuideTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_guides", stdout=StringIO())
        cls.editor = get_user_model().objects.create_superuser(username="guide-editor")

    def test_guides_use_existing_content_and_routes(self):
        call_command("bootstrap_guides", stdout=StringIO())
        self.assertEqual(GuideIndexPage.objects.count(), 1)
        self.assertEqual(DestinationGuidePage.objects.count(), 1)
        self.assertContains(self.client.get("/"), 'href="/guides/"')
        self.assertContains(self.client.get("/guides/"), 'href="/guides/norwich/"')
        self.assertContains(self.client.get("/guides/norwich/"), 'href="/tours/ea600/"')
        self.assertContains(self.client.get("/tours/ea600/"), "Cambridge")
        self.assertContains(self.client.get("/cms/", follow=True), "Sign in - Wagtail")

    def test_only_published_guide_revisions_and_tours_display(self):
        index = GuideIndexPage.objects.get()
        tour = Tour.objects.get(slug="ea600")
        guide = index.add_child(instance=DestinationGuidePage(
            title="Coastal guide",
            slug="coastal",
            introduction="Published introduction",
            live=False,
            body=[("featured_tour", tour)],
        ))
        revision = guide.save_revision()
        self.assertEqual(self.client.get("/guides/coastal/").status_code, 404)
        revision.publish()
        self.assertContains(self.client.get("/guides/coastal/"), 'href="/tours/ea600/"')

        guide.refresh_from_db()
        guide.introduction = "Private draft revision"
        guide.save_revision()
        self.assertNotContains(self.client.get("/guides/coastal/"), guide.introduction)
        self.client.force_login(self.editor)
        self.assertRedirects(
            self.client.post(reverse("builder_unpublish", args=[tour.pk]), {"version": tour_version(tour)}),
            reverse("builder_edit", args=[tour.pk]),
        )
        self.assertNotContains(self.client.get("/guides/coastal/"), 'href="/tours/ea600/"')
        tour.refresh_from_db()
        self.assertRedirects(
            self.client.post(reverse("builder_delete", args=[tour.pk]), {"version": tour_version(tour)}),
            reverse("builder_index"),
        )
        self.assertContains(self.client.get("/guides/coastal/"), "Published introduction")
        self.assertNotContains(self.client.get("/guides/coastal/"), 'href="/tours/ea600/"')

    def test_photo_uploaded_through_wagtail_can_be_used_in_django(self):
        self.client.force_login(self.editor)
        self.assertContains(self.client.get("/cms/"), "EA600 Guides")
        photo_url = reverse("guide-photo-chooser:create")
        png = BytesIO()
        Image.new("RGB", (10, 10), "green").save(png, "PNG")

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(photo_url, {
                "title": "Guide upload",
                "alt_text": "A green placeholder",
                "image": SimpleUploadedFile("guide.png", png.getvalue(), content_type="image/png"),
            })
            self.assertEqual(response.status_code, 200)
            photo = Photo.objects.get(title="Guide upload")
            tour = Tour.objects.get(slug="ea600")
            tour.cover = photo
            tour.save(update_fields=["cover"])
            self.assertContains(self.client.get(tour.get_absolute_url()), photo.url)
            media = self.client.get(photo.url)
            self.assertEqual(media.status_code, 200)
            self.assertEqual(b"".join(media.streaming_content), png.getvalue())
