from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from wagtail.admin import messages

from . import billing
from .mail import email_ready
from .models import AdvertisePageSettings, BusinessListing, PartnerApplication
from .notifications import email_payment_link


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
    listing = get_object_or_404(BusinessListing.objects.select_related("application__owner"), pk=pk)
    application = getattr(listing, "application", None)
    ready = bool(application and not listing.demo_key and application.can_checkout)
    can_email = ready and settings.PARTNER_APPLICATIONS_ENABLED and email_ready() and request.user.is_verified()
    if request.method == "POST":
        if request.POST.get("action") == "email-payment-link":
            if not can_email:
                raise PermissionDenied
            if not cache.add(f"partner-payment-link:{application.pk}", True, timeout=60):
                messages.error(request, "Wait a minute before sending another payment link.")
            elif email_payment_link(application):
                messages.success(request, "The advertiser was emailed a payment link.")
            else:
                messages.error(request, "Email delivery failed. Try again after checking the outgoing mail setup.")
            return redirect("ea600_business_listings:sandbox_payment", pk=listing.pk)
        if not can_open_sandbox:
            raise PermissionDenied
        if ready:
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
        "can_email": can_email,
        "sandbox_enabled": sandbox_enabled(),
        "can_open_sandbox": can_open_sandbox,
        "prices": billing.display_prices(AdvertisePageSettings.load(request)),
    })
