from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .release_history import load_release_notes
from .test_support import sign_in_verified


class ReleaseNotesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.admin = users.create_superuser(username="release-admin")
        cls.editor = users.create_user(username="release-editor", is_staff=True)

    def test_anonymous_and_unverified_users_must_sign_in(self):
        url = reverse("admin_release_notes")
        destination = reverse("admin:login") + f"?next={url}"
        self.assertRedirects(self.client.get(url), destination, fetch_redirect_response=False)
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")
        self.assertRedirects(self.client.get(url), destination, fetch_redirect_response=False)

    def test_verified_editors_cannot_access_release_notes(self):
        sign_in_verified(self.client, self.editor)
        url = reverse("admin_release_notes")
        self.assertNotContains(self.client.get(reverse("admin:index")), url)
        self.assertEqual(self.client.get(url).status_code, 403)

    @patch.dict("os.environ", {"RAILWAY_GIT_COMMIT_SHA": "0123456789abcdef"})
    def test_verified_superusers_can_read_the_private_history(self):
        sign_in_verified(self.client, self.admin)
        url = reverse("admin_release_notes")
        self.assertContains(self.client.get(reverse("admin:index")), f'href="{url}"')
        response = self.client.get(url)
        self.assertContains(response, "Running version")
        self.assertContains(response, "01234567</code>")
        for release in load_release_notes():
            self.assertContains(response, f'id="release-{release["version"]}"')
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_changelog_versions_are_unique_and_newest_first(self):
        releases = load_release_notes()
        versions = [tuple(map(int, release["version"].split("."))) for release in releases]
        dates = [release["date"] for release in releases]
        self.assertEqual(versions, sorted(set(versions), reverse=True))
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertTrue(all(release["title"] and release["changes"] for release in releases))
