from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import PartnerApplication


SANDBOX_SESSION = "ea600_partner_sandbox"


def sandbox_allowed(request):
    return (
        settings.PARTNER_PILOT_PREVIEW
        and settings.PARTNER_APPLICATIONS_ENABLED
        and settings.PARTNER_BILLING_MODE == PartnerApplication.BillingMode.TEST
        and request.user.is_active
        and request.user.is_superuser
        and request.user.is_verified()
    )


def sandbox_application(request):
    scope = request.session.get(SANDBOX_SESSION)
    if not scope or not sandbox_allowed(request):
        return None
    if scope["user_id"] != str(request.user.pk) or scope["expires"] <= timezone.now().timestamp():
        return None
    return PartnerApplication.objects.select_related("owner", "listing").filter(pk=scope["application_id"]).first()


@never_cache
@require_http_methods(["GET", "POST"])
def open_sandbox(request, pk):
    if not sandbox_allowed(request):
        raise PermissionDenied
    application = get_object_or_404(PartnerApplication.objects.select_related("owner", "listing"), listing_id=pk)
    listing_url = reverse("ea600_business_listings:edit", args=[application.listing_id])
    if request.method == "POST" and application.can_checkout:
        request.session[SANDBOX_SESSION] = {
            "user_id": str(request.user.pk),
            "expires": (timezone.now() + timedelta(minutes=20)).timestamp(),
            "application_id": str(application.pk),
        }
        return redirect("partners:dashboard")
    return render(request, "partners/admin/open_sandbox.html", {
        "application": application, "listing_url": listing_url,
    })
