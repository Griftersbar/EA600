import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from stripe import SignatureVerificationError, StripeError, Webhook

from siteapp.editor_auth import editor_client_ip
from siteapp.views import homepage_content

from . import billing
from .activity import record_click, with_recent_activity
from .forms import AdvertisingEnquiryForm, OwnerEmailForm, PartnerApplicationForm
from .mail import email_ready, send_partner_mail
from .models import AdvertisePageSettings, BusinessListing, ListingClick, PartnerAccount, PartnerApplication, published_placements
from .sandbox import SANDBOX_SESSION, sandbox_application


logger = logging.getLogger(__name__)
OWNER_SESSION = "ea600_partner_owner"


def show(request, template, *, status=200, **context):
    response = render(request, f"partners/{template}.html", {"homepage": homepage_content(), **context}, status=status)
    response["Referrer-Policy"] = "same-origin"
    return response


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def owner(request):
    return PartnerAccount.objects.filter(pk=request.session.get(OWNER_SESSION)).first()


def applications_enabled():
    return settings.PARTNER_APPLICATIONS_ENABLED and email_ready()


def allow_partner_request(request, purpose, limit):
    ip = editor_client_ip(request) or "unknown"
    key = f"partner-{purpose}-ip:{ip}"
    cache.add(key, 0, timeout=900)
    try:
        return cache.incr(key) <= limit
    except ValueError:
        return False


def show_advertise(request, *, form=None, enquiry_form=None, sent=False, status=200):
    page = AdvertisePageSettings.load(request)
    return show(
        request, "advertise", status=status, page_title=page.title, advertise_page=page, prices=billing.display_prices(page),
        form=form if form is not None else OwnerEmailForm(),
        enquiry_form=enquiry_form if enquiry_form is not None else AdvertisingEnquiryForm(page, prefix="enquiry"),
        enquiry_received=request.session.pop("partner_enquiry_received", False),
        enabled=applications_enabled(), signed_in=bool(owner(request)), sent=sent,
        pilot_preview=settings.PARTNER_PILOT_PREVIEW,
    )


def authenticated_application(request, pk):
    preview = sandbox_application(request)
    if preview:
        if preview.pk != pk:
            raise Http404
        return preview
    return get_object_or_404(
        PartnerApplication.objects.select_related("owner", "listing"), pk=pk,
        owner_id=request.session.get(OWNER_SESSION),
    )


@never_cache
@require_http_methods(["GET", "POST"])
def advertise(request):
    form = OwnerEmailForm(request.POST if request.method == "POST" else None)
    if applications_enabled() and request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if allow_partner_request(request, "email", 10) and cache.add(f"partner-email:{digest(email)}", True, timeout=60):
            account, _ = PartnerAccount.objects.get_or_create(email=email)
            token = secrets.token_urlsafe(32)
            token_digest = digest(token)
            PartnerAccount.objects.filter(pk=account.pk).update(
                access_digest=token_digest, access_expires=timezone.now() + timedelta(minutes=20),
            )
            link = request.build_absolute_uri(reverse("partners:access", args=[token]))
            try:
                send_partner_mail(
                    "Your EA600 business sign-in link",
                    f"Open this link within 20 minutes to sign in to EA600 Business Listings.\n\n{link}",
                    email,
                )
            except OSError:
                PartnerAccount.objects.filter(pk=account.pk, access_digest=token_digest).update(access_digest="", access_expires=None)
                logger.warning("Could not send EA600 business sign-in email")
                form.add_error(None, "Email is temporarily unavailable. Please try again shortly.")
                return show_advertise(request, form=form)
        return show_advertise(request, sent=True)
    return show_advertise(request, form=form)


@never_cache
@require_http_methods(["GET", "POST"])
def enquire(request):
    advertise_section = reverse("partners:advertise") + "#advertising-enquiry"
    if request.method == "GET":
        return redirect(advertise_section)

    form = AdvertisingEnquiryForm(AdvertisePageSettings.load(request), request.POST, prefix="enquiry")
    if not form.is_valid():
        return show_advertise(request, enquiry_form=form, status=400)
    if not allow_partner_request(request, "enquiry", 5):
        form.add_error(None, "Too many enquiries were submitted. Please try again in 15 minutes.")
        response = show_advertise(request, enquiry_form=form, status=429)
        response["Retry-After"] = "900"
        return response
    form.save()
    request.session["partner_enquiry_received"] = True
    return redirect(advertise_section)


@never_cache
@require_http_methods(["GET", "POST"])
def access(request, token):
    if not applications_enabled():
        return HttpResponseNotFound()
    accounts = PartnerAccount.objects.filter(access_digest=digest(token), access_expires__gt=timezone.now())
    account_id = accounts.values_list("pk", flat=True).first()
    if account_id and request.method == "POST":
        if accounts.filter(pk=account_id).update(access_digest="", access_expires=None):
            request.session.cycle_key()
            request.session.pop(SANDBOX_SESSION, None)
            request.session[OWNER_SESSION] = account_id
            return redirect("partners:dashboard")
        account_id = None
    return show(request, "access", valid=bool(account_id))


@never_cache
@require_POST
def sign_out(request):
    preview = sandbox_application(request)
    request.session.pop(SANDBOX_SESSION, None)
    if preview:
        return redirect("ea600_business_listings:edit", preview.listing_id)
    request.session.pop(OWNER_SESSION, None)
    request.session.cycle_key()
    return redirect("partners:advertise")


@never_cache
@require_http_methods(["GET", "POST"])
def dashboard(request):
    preview = sandbox_application(request)
    account = preview.owner if preview else owner(request)
    if not account:
        return redirect("partners:advertise")
    enabled = not preview and applications_enabled()
    form = PartnerApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and enabled and form.is_valid():
        form.create_application(account)
        return redirect("partners:dashboard")
    applications = account.applications.select_related("listing")
    if preview:
        applications = applications.filter(pk=preview.pk)
    return show(
        request, "dashboard", form=form, account=account, enabled=enabled, sandbox=bool(preview),
        applications=with_recent_activity(applications, "listing__click_days").order_by("listing__name"),
        billing_ready=billing.billing_ready(),
    )


@never_cache
@require_safe
def listing_click(request, pk, action):
    placement = get_object_or_404(published_placements(), pk=pk)
    listing = placement.listing
    if action not in (listing.link_action, ListingClick.Action.DIRECTIONS):
        raise Http404

    if listing.demo_key:
        destination = reverse("partners:pilot") + f"#listing-{listing.pk}"
    else:
        destination = listing.directions_url if action == ListingClick.Action.DIRECTIONS else listing.link
        try:
            target = urlsplit(destination)
            if target.scheme not in ("http", "https") or not target.hostname:
                raise Http404
        except ValueError as error:
            raise Http404 from error

    purpose = request.headers.get("Sec-Purpose", request.headers.get("Purpose", "")).lower()
    if request.method == "GET" and "prefetch" not in purpose and "prerender" not in purpose:
        try:
            record_click(listing.pk, action)
        except DatabaseError:
            logger.warning("Could not count a business listing click")
    response = redirect(destination)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@never_cache
@require_safe
def pilot(request):
    if not settings.PARTNER_PILOT_PREVIEW:
        raise Http404
    demo_ids = published_placements().filter(listing__demo_key__isnull=False).values("listing_id")
    listings = with_recent_activity(BusinessListing.objects.filter(pk__in=demo_ids))
    response = show(request, "pilot", listings=listings)
    response["X-Robots-Tag"] = "noindex"
    return response


@never_cache
@require_http_methods(["GET", "POST"])
def start_checkout(request, pk):
    application = authenticated_application(request, pk)
    if not application.approved:
        return show(request, "billing_error", status=409, error="Checkout is unavailable for this listing.")
    if not application.can_checkout:
        return redirect("partners:dashboard")
    if request.method == "GET":
        return show(
            request, "payment", page_title="Choose a listing subscription · EA600", application=application,
            prices=billing.display_prices(AdvertisePageSettings.load(request)), test_mode=not billing.live_billing(),
            billing_ready=billing.billing_ready(),
        )
    if not billing.billing_ready():
        return show(request, "billing_error", status=409, error="Checkout is unavailable for this listing.")
    plan = request.POST.get("plan")
    if plan not in billing.PLANS:
        return HttpResponseBadRequest("Choose a monthly or annual plan.")
    return_url = request.build_absolute_uri(reverse("partners:dashboard"))
    try:
        url = billing.checkout(application, plan, return_url, request.build_absolute_uri(request.path))
    except billing.BillingUnavailable as error:
        return show(request, "billing_error", error=str(error))
    except StripeError as error:
        logger.warning("Stripe checkout request failed (%s, HTTP %s)", type(error).__name__, error.http_status)
        return show(request, "billing_error", status=503, error="Checkout is temporarily unavailable. Please try again.")
    return redirect(url or "partners:dashboard")


@never_cache
@require_POST
def portal(request, pk):
    application = authenticated_application(request, pk)
    if not billing.billing_ready() or not application.has_current_billing_mode or not application.stripe_customer_id:
        return HttpResponse("Billing is unavailable for this listing.", status=409)
    try:
        session = billing.stripe_client().v1.billing_portal.sessions.create({
            "customer": application.stripe_customer_id,
            "return_url": request.build_absolute_uri(reverse("partners:dashboard")),
        })
    except StripeError:
        logger.warning("Stripe billing portal request failed")
        return show(request, "billing_error", error="Billing is temporarily unavailable. Please try again.")
    return redirect(session.url)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not billing.billing_ready():
        return HttpResponseNotFound()
    try:
        event = Webhook.construct_event(request.body, request.headers.get("Stripe-Signature", ""), billing.webhook_secret())
    except (ValueError, SignatureVerificationError):
        return HttpResponseBadRequest("Invalid Stripe event.")
    if event.get("livemode") is not billing.live_billing():
        return HttpResponseBadRequest("The Stripe event does not match the billing mode.")
    try:
        billing.apply_event(event)
    except StripeError:
        logger.warning("Stripe webhook synchronization failed")
        return HttpResponse(status=503)
    return HttpResponse(status=204)
