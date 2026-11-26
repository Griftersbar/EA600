import logging
import secrets
from contextlib import nullcontext
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from django.db import DatabaseError, OperationalError, transaction
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
from .access_tokens import digest
from .activity import record_click, with_recent_activity
from .forms import (
    AdvertisingEnquiryForm, GuestPartnerApplicationForm, OwnerEmailForm, PartnerApplicationForm, PartnerListingEditForm,
)
from .mail import applications_enabled, email_url, send_partner_mail
from .models import (
    AdvertisePageSettings, BusinessListing, ListingClick, PartnerAccount, PartnerApplication,
    PendingPartnerApplication, published_placements,
)
from .notifications import notify_application_received
from .sandbox import SANDBOX_SESSION, sandbox_application


logger = logging.getLogger(__name__)
OWNER_SESSION = "ea600_partner_owner"


def show(request, template, *, status=200, **context):
    response = render(request, f"partners/{template}.html", {"homepage": homepage_content(), **context}, status=status)
    response["Referrer-Policy"] = "strict-origin" if template in {"access", "confirm_link"} else "same-origin"
    return response


def owner(request):
    return PartnerAccount.objects.filter(pk=request.session.get(OWNER_SESSION)).first()


def sign_in_owner(request, account_id):
    request.session.cycle_key()
    request.session.pop(SANDBOX_SESSION, None)
    request.session[OWNER_SESSION] = account_id


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
        if not allow_partner_request(request, "email", 10):
            return show_advertise(request, sent=True)
        account = PartnerAccount.objects.filter(email=email).first()
        if account and cache.add(f"partner-email:{digest(email)}", True, timeout=60):
            token = secrets.token_urlsafe(32)
            token_digest = digest(token)
            PartnerAccount.objects.filter(pk=account.pk).update(
                access_digest=token_digest, access_expires=timezone.now() + timedelta(minutes=20),
            )
            link = email_url(reverse("partners:access", args=[token]), request=request)
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
def apply(request):
    if not applications_enabled():
        return redirect("partners:advertise")
    form = GuestPartnerApplicationForm(request.POST or None, request.FILES or None, placement=request.GET)
    if owner(request):
        return redirect(reverse(
            "partners:dashboard", query=form.placement_query, fragment="apply-for-listing",
        ))

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if not allow_partner_request(request, "application", 5) or not cache.add(
            f"partner-submit:{digest(email)}", True, timeout=60,
        ):
            form.add_error(None, "Please wait a moment before sending another application.")
            return show(request, "apply", form=form, status=429)

        PendingPartnerApplication.objects.filter(expires_at__lte=timezone.now()).delete()
        token = secrets.token_urlsafe(32)
        photo_form = form.cleaned_data["photo_upload"]
        photo = photo_form.cleaned_data["image"] if photo_form else None
        if photo:
            photo.seek(0)
        submission = PendingPartnerApplication.objects.create(
            email=email, verification_digest=digest(token), expires_at=timezone.now() + timedelta(days=1),
            details=form.submission_details(), photo=photo or "",
        )
        url = email_url(reverse("partners:confirm_application", args=[token]), request=request)
        try:
            send_partner_mail(
                "Confirm your EA600 business email",
                f"Confirm your email to submit your listing for {form.cleaned_data['name']}. "
                f"Your link is valid for 24 hours.\n\n{url}",
                email,
            )
        except OSError:
            submission.delete()
            cache.delete(f"partner-submit:{digest(email)}")
            logger.warning("Could not send EA600 listing email verification")
            form.add_error(None, "Email is temporarily unavailable. Please try again shortly.")
            return show(request, "apply", form=form, status=503)
        return show(request, "apply", sent=True)
    return show(request, "apply", form=form)


@never_cache
@require_http_methods(["GET", "POST"])
def confirm_application(request, token):
    if not applications_enabled():
        return HttpResponseNotFound()
    pending = PendingPartnerApplication.objects.filter(verification_digest=digest(token), expires_at__gt=timezone.now())
    context = {
        "title": "Confirm your business email",
        "action": "Confirm and submit listing",
        "recovery_url": reverse("partners:apply"),
    }
    if request.method == "GET":
        return show(request, "confirm_link", valid=pending.exists(), **context)

    try:
        with transaction.atomic():
            submission = pending.select_for_update().first()
            if not submission:
                return show(request, "confirm_link", **context)
            with submission.photo.open("rb") if submission.photo else nullcontext() as photo:
                files = {"photo_upload": UploadedFile(photo, name=photo.name, size=photo.size)} if photo else None
                form = PartnerApplicationForm(submission.details, files)
                if not form.is_valid():
                    return show(request, "confirm_link", error="Your listing details need updating. Please submit a new application.", **context)
                account, _ = PartnerAccount.objects.get_or_create(email=submission.email)
                application = form.create_application(account)
            submission.delete()
            transaction.on_commit(lambda: notify_application_received(application))
    except OperationalError as error:
        if "locked" not in str(error).lower():
            raise
        return show(request, "confirm_link", valid=True, error="A submission is in progress. Try again shortly.", status=409, **context)
    except FileNotFoundError:
        return show(request, "confirm_link", error="Your application photo is unavailable. Please submit a new application.", **context)
    sign_in_owner(request, account.pk)
    return redirect("partners:dashboard")


@never_cache
@require_http_methods(["GET", "POST"])
def approve_access(request, token):
    if not applications_enabled():
        return HttpResponseNotFound()
    links = PartnerApplication.objects.filter(payment_digest=digest(token), payment_link_expires__gt=timezone.now())
    application = links.select_related("listing").first()
    valid = bool(application and application.can_checkout)
    if valid and request.method == "POST":
        if links.filter(pk=application.pk).update(payment_digest="", payment_link_expires=None):
            sign_in_owner(request, application.owner_id)
            return redirect("partners:checkout", pk=application.pk)
        valid = False
    return show(
        request, "confirm_link", valid=valid, title="Your EA600 listing is approved",
        action="Continue to payment options",
        recovery_url=reverse("partners:advertise") + "#business-listing-access",
    )


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
            sign_in_owner(request, account_id)
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
    form = PartnerApplicationForm(request.POST or None, request.FILES or None, placement=request.GET if enabled else None)
    if request.method == "POST" and enabled and form.is_valid():
        application = form.create_application(account)
        transaction.on_commit(lambda: notify_application_received(application))
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
@require_http_methods(["GET", "POST"])
def edit_listing(request, pk):
    application = get_object_or_404(
        PartnerApplication.objects.select_related("listing"), pk=pk, owner_id=request.session.get(OWNER_SESSION),
    )
    with transaction.atomic():
        listing = BusinessListing.objects.select_for_update().get(pk=application.listing_id)
        draft = listing.get_latest_revision_as_object()
        form = PartnerListingEditForm(request.POST or None, request.FILES or None, instance=draft)
        revision = str(listing.latest_revision_id or "")
        if request.method == "POST" and form.is_valid():
            if listing.locked or listing.workflow_in_progress or request.POST.get("revision") != revision:
                form.add_error(None, "This listing changed or is being reviewed. Open your listing again to continue.")
                return show(request, "edit_listing", form=form, listing=listing, revision=revision, status=409)
            form.save_draft()
            return redirect(reverse("partners:dashboard") + "?listing=updated")
    return show(request, "edit_listing", form=form, listing=listing, revision=revision)
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
