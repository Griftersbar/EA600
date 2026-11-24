from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import TestCase
from django.urls import reverse

from .models import FAQ, HomeContent, Photo, PlanningTip, Story, Tour


class EditorialCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(username="cms-editor")

    def setUp(self):
        self.client.force_login(self.editor)

    def form_data(self, url, instance):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        fields = response.context["form"].fields
        return {name: "" if value is None else value for name, value in model_to_dict(instance, fields).items()}

    def test_homepage_and_site_settings_update_the_same_content(self):
        content = HomeContent.objects.get()
        tour = Tour.objects.create(title="Coast weekend", slug="coast-weekend", summary="Coast", is_published=True)
        homepage = reverse("ea600_homepage:edit")
        settings = reverse("ea600_site_settings:edit")
        homepage_data = self.form_data(homepage, content)
        settings_data = self.form_data(settings, content)
        self.assertEqual(
            set(homepage_data) | set(settings_data),
            set(model_to_dict(content)) - {"id"},
        )
        self.assertTrue(set(homepage_data).isdisjoint(settings_data))

        updated = {"site_title": "EA600 Coastal", "contact_email": "coast@example.test"}
        self.assertRedirects(self.client.post(settings, {**settings_data, **updated}), settings)
        changed = {"featured_tour": tour.pk, "hero_title": "Explore the coast"}
        self.assertRedirects(self.client.post(homepage, {**homepage_data, **changed}), homepage)
        content.refresh_from_db()
        self.assertEqual(content.featured_tour, tour)
        home = self.client.get("/")
        self.assertContains(home, "Explore the coast")
        self.assertContains(home, "EA600 Coastal")
        self.assertContains(home, "mailto:coast@example.test")

    def test_homepage_rejects_new_draft_tour_selection(self):
        content = HomeContent.objects.get()
        old_featured = content.featured_tour
        draft = Tour.objects.create(title="Unfinished", slug="unfinished", summary="Still editing")
        url = reverse("ea600_homepage:edit")
        result = self.client.post(url, {**self.form_data(url, content), "featured_tour": draft.pk})
        self.assertFormError(result.context["form"], "featured_tour", "Choose a published tour.")
        content.refresh_from_db()
        self.assertEqual(content.featured_tour, old_featured)

    def test_wagtail_editors_require_homepage_change_permission(self):
        staff = get_user_model().objects.create_user(username="limited-editor", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="access_admin"))
        self.client.force_login(staff)
        for url in ("/cms/homepage/", "/cms/site-settings/"):
            self.assertEqual(self.client.get(url).status_code, 302)
        staff.user_permissions.add(Permission.objects.get(codename="change_homecontent"))
        for url in ("/cms/homepage/", "/cms/site-settings/"):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_content_menu_models_publish_existing_pages(self):
        photo = Photo.objects.first()
        self.assertContains(self.client.get("/cms/"), "Content")
        for path in ("destinations", "planning-tips", "stories", "faqs", "highlights", "footer-photos"):
            self.assertEqual(self.client.get(f"/cms/{path}/").status_code, 200)

        self.assertEqual(self.client.post("/cms/planning-tips/add/", {
            "title": "Leave time for the coast", "description": "Make time for the pier.",
            "photo": photo.pk, "position": 0,
        }).status_code, 302)
        self.assertTrue(PlanningTip.objects.filter(title="Leave time for the coast").exists())
        self.assertEqual(self.client.post("/cms/faqs/add/", {
            "question": "Where can I start?", "answer": "Start in Norwich.", "position": 0,
        }).status_code, 302)
        self.assertTrue(FAQ.objects.filter(question="Where can I start?").exists())

        data = {"title": "Along the coast", "slug": "along-the-coast", "excerpt": "Our story", "position": 0}
        self.assertEqual(self.client.post("/cms/stories/add/", data).status_code, 302)
        story = Story.objects.get(slug=data["slug"])
        self.assertEqual(self.client.get(story.get_absolute_url()).status_code, 404)
        edit = f"/cms/stories/edit/{story.pk}/"
        self.assertEqual(self.client.post(edit, {**data, "is_published": "on"}).status_code, 302)
        self.assertContains(self.client.get(story.get_absolute_url()), "Along the coast")

        home = self.client.get("/")
        self.assertContains(home, "Leave time for the coast")
        self.assertContains(home, "Where can I start?")
        self.assertContains(home, 'href="/stories/along-the-coast/"')

    def test_photo_library_lists_existing_images_and_searches_their_alt_text(self):
        photo = Photo.objects.get(bundled_path="assets/images/norwich.webp")
        photo.alt_text = "Norwich market from above"
        photo.save(update_fields=["alt_text"])
        other = Photo.objects.exclude(pk=photo.pk).first()
        self.assertContains(self.client.get("/cms/"), "EA600 Photos")

        result = self.client.get(reverse("ea600_photos:index"), {"q": photo.alt_text})
        self.assertContains(result, photo.alt_text)
        self.assertContains(result, f'src="{photo.url}"')
        self.assertNotContains(result, f'src="{other.url}"')

    def test_photo_uploaded_in_the_library_is_available_to_tour_builder(self):
        photo_data = BytesIO()
        Image.new("RGB", (8, 8), "green").save(photo_data, "PNG")
        index = reverse("ea600_photos:index")
        add = reverse("ea600_photos:add")
        self.assertContains(self.client.get(index), "Add photo")
        self.assertContains(self.client.get(add), 'type="file" name="image"')

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            result = self.client.post(add, {
                "title": "Coastal photo", "alt_text": "Path by the sea",
                "image": SimpleUploadedFile("coast.png", photo_data.getvalue(), content_type="image/png"),
            })
            self.assertRedirects(result, index)
            photo = Photo.objects.get(title="Coastal photo")
            self.assertContains(self.client.get(index, {"q": photo.title}), f'src="{photo.url}"')
            self.assertEqual(self.client.get(photo.url).status_code, 200)

            edit = reverse("ea600_photos:edit", args=[photo.pk])
            result = self.client.post(edit, {"title": "New coastal photo", "alt_text": "Footpath along the coast"})
            self.assertRedirects(result, index)
            photo.refresh_from_db()
            self.assertEqual(photo.alt_text, "Footpath along the coast")
            result = self.client.get(reverse("builder_photos"), {"q": photo.title})
            self.assertEqual(result.json()["photos"], [{"id": photo.pk, "title": photo.title, "url": photo.url}])
