from datetime import timedelta

from axes.models import AccessAttempt
from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from .editor_auth import PENDING_SIGN_IN


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EditorMFATests(TestCase):
    password = "Local-only-editor-test-password"

    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(
            username="mfa-editor", password=cls.password,
        )

    def start_sign_in(self, entry="wagtailadmin_login", destination="", client=None):
        client = client or self.client
        response = client.post(reverse(entry), {
            "username": self.editor.username, "password": self.password, "next": destination,
        })
        self.assertRedirects(response, reverse("editor_verify"), fetch_redirect_response=False)
        return reverse("editor_verify")

    def test_enrollment_requires_a_code_before_opening_any_editor(self):
        verify = self.start_sign_in(destination="/builder/tours/")
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get("/builder/tours/").status_code, 302)
        self.assertEqual(self.client.get("/cms/").status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        response = self.client.get(verify)
        self.assertContains(response, "Set up your authenticator")
        self.assertContains(response, "data:image/svg+xml")
        self.assertIn("no-store", response.headers["Cache-Control"])
        key = self.client.session[PENDING_SIGN_IN]["setup_key"]
        device = TOTPDevice(key=key)

        code = f"{totp(device.bin_key):06}"
        result = self.client.post(verify, {"code": code})
        self.assertRedirects(result, reverse("editor_recovery_codes"), fetch_redirect_response=False)
        self.assertTrue(TOTPDevice.objects.filter(user=self.editor, confirmed=True).exists())
        recovery = self.client.get(result["Location"])
        self.assertContains(recovery, "Save your recovery codes")
        self.assertContains(recovery, 'href="/builder/tours/"')
        self.assertEqual(len(recovery.context["codes"]), 10)
        self.assertIn("no-store", recovery.headers["Cache-Control"])
        self.assertEqual(self.client.get(result["Location"]).status_code, 302)
        for path in ("/builder/tours/", "/cms/", "/admin/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_existing_authenticator_and_one_time_recovery_work_from_admin(self):
        device = TOTPDevice.objects.create(user=self.editor, name="Phone", tolerance=0)
        verify = self.start_sign_in("admin:login", "/cms/")
        self.assertContains(self.client.get(verify), "Verify your sign-in")
        self.assertRedirects(self.client.post(verify, {"code": f"{totp(device.bin_key):06}"}), "/cms/")
        self.client.post(reverse("admin:logout"))

        backup = self.editor.staticdevice_set.create(name="Recovery codes")
        code = "90c70c9a8183bff5"
        StaticToken.objects.create(device=backup, token=code)
        verify = self.start_sign_in("admin:login", "/builder/tours/") + "?recovery=1"
        self.assertContains(self.client.get(verify), "Use a recovery code")
        self.assertRedirects(self.client.post(verify, {"code": code}), "/builder/tours/")
        self.assertFalse(StaticToken.objects.filter(device=backup).exists())
        self.client.post(reverse("admin:logout"))
        self.start_sign_in()
        self.assertContains(self.client.post(verify, {"code": code}), "That code could not be verified")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_authenticator_failures_are_throttled_on_the_device(self):
        device = TOTPDevice.objects.create(user=self.editor, name="Phone", tolerance=0)
        verify = self.start_sign_in()
        code = totp(device.bin_key)
        self.assertContains(
            self.client.post(verify, {"code": f"{(code + 1) % 1000000:06}"}),
            "That code could not be verified",
        )
        throttled = self.client.post(verify, {"code": f"{code:06}"})
        self.assertContains(throttled, "Too many attempts", status_code=429)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_password_failures_are_shared_between_login_routes(self):
        paths = (reverse("admin:login"), reverse("wagtailadmin_login"))
        for attempt in range(5):
            result = self.client.post(paths[attempt % 2], {
                "username": self.editor.username, "password": "wrong-password",
            }, REMOTE_ADDR=f"192.0.2.{attempt + 1}")
            self.assertEqual(result.status_code, 429 if attempt == 4 else 200)
        self.assertIn("no-store", result.headers["Cache-Control"])
        self.assertEqual(result.headers["Retry-After"], "900")
        blocked = self.client.post(paths[1], {
            "username": self.editor.username, "password": self.password,
        }, REMOTE_ADDR="192.0.2.10")
        self.assertEqual(blocked.status_code, 429)
        self.assertNotIn(PENDING_SIGN_IN, self.client.session)

        AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))
        self.start_sign_in("admin:login")

    def test_ip_limit_counts_attempts_with_different_usernames(self):
        paths = (reverse("admin:login"), reverse("wagtailadmin_login"))
        for attempt in range(5):
            result = self.client.post(paths[attempt % 2], {
                "username": f"unknown-editor-{attempt}", "password": "wrong-password",
            })
        self.assertEqual(result.status_code, 429)
        self.assertEqual(self.client.post(paths[0], {
            "username": self.editor.username, "password": self.password,
        }).status_code, 429)

    def test_sessions_without_mfa_must_sign_in_again(self):
        self.client.force_login(self.editor, backend="django.contrib.auth.backends.ModelBackend")
        for path, login in (
            ("/admin/", "/admin/login/"),
            ("/builder/tours/", "/admin/login/"),
            ("/cms/", "/cms/login/"),
        ):
            self.assertRedirects(self.client.get(path), f"{login}?next={path}", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_password_change_invalidates_a_pending_sign_in(self):
        verify = self.start_sign_in()
        self.editor.set_password("Changed-local-test-password")
        self.editor.save()
        self.assertRedirects(self.client.get(verify), "/cms/login/?next=/cms/", fetch_redirect_response=False)
        self.assertNotIn(PENDING_SIGN_IN, self.client.session)

    def test_password_and_enrollment_are_scoped_to_the_same_browser(self):
        verify = self.start_sign_in(destination="https://external.example/")
        another_browser = Client()
        self.assertRedirects(another_browser.get(verify), "/admin/login/", fetch_redirect_response=False)
        self.assertEqual(self.client.session[PENDING_SIGN_IN]["destination"], "/cms/")

    def test_sign_in_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for route in ("admin:login", "wagtailadmin_login"):
            self.assertEqual(client.post(reverse(route), {
                "username": self.editor.username, "password": self.password,
            }).status_code, 403)
