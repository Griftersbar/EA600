import os
from base64 import b32encode
from ipaddress import ip_address
from secrets import token_hex
from time import time

import segno
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods, require_safe
from django_otp import login as login_with_device
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from wagtail.admin.views.account import password_reset_enabled

PENDING_SIGN_IN = "editor_pending_sign_in"
RECOVERY_CODES = "editor_recovery_codes"
SIGN_IN_TIMEOUT = 600
LOGIN_ROUTES = {"django": "admin:login", "wagtail": "wagtailadmin_login"}
EDITOR_HOMES = {"django": "admin:index", "wagtail": "wagtailadmin_home"}


def editor_client_ip(request):
    address = request.META.get("REMOTE_ADDR")
    public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    host = request.META.get("HTTP_HOST", "").lower().removesuffix(":443")
    # Railway overwrites X-Real-IP at the public HTTP edge for this domain.
    if not settings.DEBUG and public_domain and host == public_domain:
        address = request.META.get("HTTP_X_REAL_IP") or address
    try:
        return str(ip_address(address))
    except ValueError:
        return None


@never_cache
def password_lockout(request, original_response=None, credentials=None):
    response = render(request, "siteapp/editor_auth/locked.html", status=429)
    response["Retry-After"] = str(int(settings.AXES_COOLOFF_TIME.total_seconds()))
    return response


class EditorMFAMiddleware:
    """Require a verified device even for sessions established before MFA was enabled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith(("/admin/", "/cms/", "/builder/")) and path not in {
            "/admin/login/", "/admin/logout/", "/cms/login/", "/cms/logout/",
        }:
            if request.user.is_authenticated and not request.user.is_verified():
                entry = "wagtail" if path.startswith("/cms/") else "django"
                response = redirect_to_login(request.get_full_path(), reverse(LOGIN_ROUTES[entry]))
                add_never_cache_headers(response)
                return response
        return self.get_response(request)


def can_enter(user, entry):
    if entry == "wagtail":
        return user.has_perm("wagtailadmin.access_admin")
    return user.is_staff


class EditorPasswordForm(AuthenticationForm):
    def __init__(self, request, *args, entry, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.entry = entry
        if entry == "wagtail":
            self.fields["remember"] = forms.BooleanField(label="Keep me signed in", required=False)

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not can_enter(user, self.entry):
            raise self.get_invalid_login_error()


class AuthenticatorCodeForm(forms.Form):
    code = forms.RegexField(
        r"^[0-9]{6}$", label="Authenticator code", max_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True}),
        error_messages={"invalid": "Enter the six digits shown in your authenticator app."},
    )


class RecoveryCodeForm(forms.Form):
    code = forms.RegexField(
        r"^[0-9a-fA-F]{16}$", label="Recovery code", max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "autofocus": True}),
        error_messages={"invalid": "Enter one of your 16-character recovery codes."},
    )


@never_cache
@sensitive_post_parameters("password")
@require_http_methods(["GET", "POST"])
def editor_login(request, entry):
    destination = request.POST.get("next", request.GET.get("next", ""))
    if not url_has_allowed_host_and_scheme(
        destination, {request.get_host()}, require_https=request.is_secure(),
    ):
        destination = reverse(EDITOR_HOMES[entry])

    if request.user.is_authenticated and request.user.is_verified() and can_enter(request.user, entry):
        return redirect(destination)

    form = EditorPasswordForm(
        request, request.POST if request.method == "POST" else None, entry=entry,
    )
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        request.session.cycle_key()
        request.session[PENDING_SIGN_IN] = {
            "user_id": user.pk, "backend": user.backend, "password_hash": user.get_session_auth_hash(),
            "entry": entry, "destination": destination, "expires": int(time()) + SIGN_IN_TIMEOUT,
            "browser_session": entry == "wagtail" and not form.cleaned_data["remember"],
        }
        return redirect("editor_verify")

    return render(request, "siteapp/editor_auth/login.html", {
        "form": form, "destination": destination, "entry": entry,
        "show_password_reset": entry == "wagtail" and password_reset_enabled(),
    })


@sensitive_variables()
def finish_sign_in(request, user, device, pending, codes=None):
    request.session.pop(PENDING_SIGN_IN, None)
    login(request, user, backend=pending["backend"])
    login_with_device(request, device)
    request.session.set_expiry(0 if pending["browser_session"] else None)
    if codes:
        request.session[RECOVERY_CODES] = {"codes": codes, "destination": pending["destination"]}
        return redirect("editor_recovery_codes")
    return redirect(pending["destination"])


@sensitive_variables()
def verify_enrollment(device, code):
    # django-otp records failed attempts on the device. Until enrollment
    # succeeds, keep the seed and failure counter in this sign-in session.
    with transaction.atomic():
        if not device.verify_token(code):
            transaction.set_rollback(True)
            return None
        StaticDevice.objects.filter(user=device.user).delete()
        backup = StaticDevice.objects.create(user=device.user, name="Recovery codes")
        codes = [token_hex(8) for _ in range(10)]
        StaticToken.objects.bulk_create(StaticToken(device=backup, token=code) for code in codes)
        return codes


def restart_sign_in(request, pending):
    request.session.pop(PENDING_SIGN_IN, None)
    return redirect_to_login(pending["destination"], reverse(LOGIN_ROUTES[pending["entry"]]))


@never_cache
@sensitive_post_parameters("code")
@sensitive_variables()
@require_http_methods(["GET", "POST"])
@transaction.atomic
def editor_verify(request):
    pending = request.session.get(PENDING_SIGN_IN)
    if not pending:
        return redirect("admin:login")

    submitting = request.method == "POST"
    users = get_user_model().objects
    if submitting:
        users = users.select_for_update()
    user = users.filter(pk=pending["user_id"], is_active=True).first()
    if (
        not user or pending["expires"] <= int(time()) or not can_enter(user, pending["entry"])
        or not constant_time_compare(pending["password_hash"], user.get_session_auth_hash())
    ):
        return restart_sign_in(request, pending)

    authenticator = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if authenticator and "setup_key" in pending:
        return restart_sign_in(request, pending)
    enrolling = authenticator is None
    recovering = not enrolling and request.GET.get("recovery") == "1"
    if enrolling:
        authenticator = TOTPDevice(user=user, name="Authenticator app")
        if "setup_key" not in pending:
            pending["setup_key"] = authenticator.key
            request.session[PENDING_SIGN_IN] = pending
        authenticator.key = pending["setup_key"]
        device = authenticator
    elif recovering:
        device = StaticDevice.objects.filter(user=user, confirmed=True).first()
    else:
        device = authenticator

    form_class = RecoveryCodeForm if recovering else AuthenticatorCodeForm
    form = form_class(request.POST if submitting else None)
    status = 200
    if submitting and form.is_valid():
        code = form.cleaned_data["code"].lower()
        if enrolling:
            codes = verify_enrollment(device, code)
            if codes:
                return finish_sign_in(request, user, device, pending, codes=codes)
            pending["setup_failures"] = pending.get("setup_failures", 0) + 1
            if pending["setup_failures"] >= 5:
                return restart_sign_in(request, pending)
            request.session[PENDING_SIGN_IN] = pending
        elif device and not device.verify_is_allowed()[0]:
            form.add_error(None, "Too many attempts. Wait a moment before entering another code.")
            status = 429
        elif device and device.verify_token(code):
            return finish_sign_in(request, user, device, pending)
        if not form.errors:
            form.add_error("code", "That code could not be verified. Try another code.")

    context = {
        "form": form, "enrolling": enrolling, "recovering": recovering,
        "has_recovery_codes": not enrolling and StaticToken.objects.filter(
            device__user=user, device__confirmed=True,
        ).exists(),
        "restart_url": reverse(LOGIN_ROUTES[pending["entry"]]),
    }
    if enrolling:
        context["qr_image"] = segno.make_qr(authenticator.config_url).svg_data_uri(scale=5, light="#fff")
        context["setup_key"] = b32encode(authenticator.bin_key).decode("ascii")
    return render(request, "siteapp/editor_auth/verify.html", context, status=status)


@never_cache
@require_safe
def editor_recovery_codes(request):
    if not request.user.is_authenticated or not request.user.is_verified():
        return redirect("admin:login")
    recovery = request.session.pop(RECOVERY_CODES, None)
    if not recovery:
        return redirect("admin:index" if request.user.is_staff else "wagtailadmin_home")
    return render(request, "siteapp/editor_auth/recovery_codes.html", recovery)
