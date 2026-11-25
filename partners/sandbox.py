from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import billing
from .models import AdvertisePageSettings, BusinessListing, PartnerApplication


SANDBOX_SESSION = "ea600_partner_sandbox"


def sandbox_enabled():
    return settings.PARTNER_PILOT_PREVIEW and settings.PARTNER_BILLING_MODE == PartnerApplication.BillingMode.TEST


def sandbox_allowed(request):
    return (
        sandbox_enabled()
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
def advertiser_payments(request, pk):
    if not request.user.has_perm("partners.change_businesslisting"):
        raise PermissionDenied
    can_open_sandbox = sandbox_allowed(request)
    if request.method == "POST" and not can_open_sandbox:
        raise PermissionDenied

    listing = get_object_or_404(BusinessListing.objects.select_related("application__owner"), pk=pk)
    application = getattr(listing, "application", None)
    ready = bool(application and not listing.demo_key and application.can_checkout)
    if request.method == "POST" and ready:
        request.session[SANDBOX_SESSION] = {
            "user_id": str(request.user.pk),
            "expires": (timezone.now() + timedelta(minutes=20)).timestamp(),
            "application_id": str(application.pk),
        }
        return redirect("partners:dashboard")

    return render(request, "partners/admin/advertiser_payments.html", {
        "listing": listing,
        "listing_url": reverse("ea600_business_listings:edit", args=[listing.pk]),
        "application": application,
        "advertiser_email": application.owner.email if application and request.user.is_superuser else "",
        "ready": ready,
        "sandbox_enabled": sandbox_enabled(),
        "can_open_sandbox": can_open_sandbox,
        "prices": billing.display_prices(AdvertisePageSettings.load(request)),
    })
