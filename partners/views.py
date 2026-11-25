import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from stripe import SignatureVerificationError, StripeError, Webhook

from siteapp.editor_auth import editor_client_ip
from siteapp.views import homepage_content

from . import billing
from .forms import OwnerEmailForm, PartnerApplicationForm
from .mail import email_ready, send_partner_mail
from .models import PartnerAccount, PartnerApplication


logger = logging.getLogger(__name__)
OWNER_SESSION = "ea600_partner_owner"


def show(request, template, **context):
    response = render(request, f"partners/{template}.html", {"homepage": homepage_content(), **context})
    response["Referrer-Policy"] = "same-origin"
    return response


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def owner(request):
    return PartnerAccount.objects.filter(pk=request.session.get(OWNER_SESSION)).first()


def applications_enabled():
    return settings.PARTNER_APPLICATIONS_ENABLED and email_ready()


def authenticated_application(request, pk):
    return get_object_or_404(
        PartnerApplication.objects.select_related("owner", "listing"), pk=pk,
        owner_id=request.session.get(OWNER_SESSION),
    )


@never_cache
@require_http_methods(["GET", "POST"])
def advertise(request):
    form = OwnerEmailForm(request.POST if request.method == "POST" else None)
    enabled = applications_enabled()
    if enabled and request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        ip = editor_client_ip(request) or "unknown"
        ip_key = f"partner-email-ip:{ip}"
        cache.add(ip_key, 0, timeout=900)
        try:
            allowed = cache.incr(ip_key) <= 10
        except ValueError:
            allowed = False
        if allowed and cache.add(f"partner-email:{digest(email)}", True, timeout=60):
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
                return show(request, "advertise", form=form, enabled=enabled, signed_in=bool(owner(request)))
        return show(request, "advertise", sent=True, enabled=enabled)
    return show(request, "advertise", form=form, enabled=enabled, signed_in=bool(owner(request)))


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
            request.session[OWNER_SESSION] = account_id
            return redirect("partners:dashboard")
        account_id = None
    return show(request, "access", valid=bool(account_id))


@never_cache
@require_POST
def sign_out(request):
    request.session.pop(OWNER_SESSION, None)
    request.session.cycle_key()
    return redirect("partners:advertise")


@never_cache
@require_http_methods(["GET", "POST"])
def dashboard(request):
    account = owner(request)
    if not account:
        return redirect("partners:advertise")
    form = PartnerApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and applications_enabled() and form.is_valid():
        with transaction.atomic():
            listing = form.save(commit=False)
            photo_form = form.cleaned_data["photo_upload"]
            if photo_form:
                listing.photo = photo_form.save()
            listing.requires_subscription = True
            listing.save()
            listing.stops = [form.cleaned_data["stop"]]
            listing.save_revision()
            # Persist the initial placement so Wagtail can list and edit the new draft.
            listing.save(update_fields=["stops"])
            PartnerApplication.objects.create(listing=listing, owner=account)
        return redirect("partners:dashboard")
    return show(
        request, "dashboard", form=form, account=account, enabled=applications_enabled(),
        applications=account.applications.select_related("listing").order_by("listing__name"),
        billing_ready=billing.billing_ready(),
    )


@never_cache
@require_POST
def start_checkout(request, pk):
    application = authenticated_application(request, pk)
    plan = request.POST.get("plan")
    if plan not in billing.PLANS:
        return HttpResponseBadRequest("Choose a monthly or annual plan.")
    if not billing.billing_ready() or not application.approved:
        return HttpResponse("Checkout is unavailable for this listing.", status=409)
    return_url = request.build_absolute_uri(reverse("partners:dashboard"))
    try:
        url = billing.checkout(application, plan, return_url)
    except billing.BillingUnavailable as error:
        return show(request, "billing_error", error=str(error))
    except StripeError:
        logger.warning("Stripe test checkout request failed")
        return show(request, "billing_error", error="Checkout is temporarily unavailable. Please try again.")
    return redirect(url or "partners:dashboard")


@never_cache
@require_POST
def portal(request, pk):
    application = authenticated_application(request, pk)
    if not billing.billing_ready() or not application.stripe_customer_id:
        return HttpResponse("Billing is unavailable for this listing.", status=409)
    try:
        session = billing.stripe_client().v1.billing_portal.sessions.create({
            "customer": application.stripe_customer_id,
            "return_url": request.build_absolute_uri(reverse("partners:dashboard")),
        })
    except StripeError:
        logger.warning("Stripe test billing portal request failed")
        return show(request, "billing_error", error="Billing is temporarily unavailable. Please try again.")
    return redirect(session.url)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not billing.billing_ready():
        return HttpResponseNotFound()
    try:
        event = Webhook.construct_event(request.body, request.headers.get("Stripe-Signature", ""), settings.STRIPE_TEST_WEBHOOK_SECRET)
    except (ValueError, SignatureVerificationError):
        return HttpResponseBadRequest("Invalid Stripe event.")
    if event.get("livemode") is not False:
        return HttpResponseBadRequest("Send a Stripe test event.")
    try:
        billing.apply_event(event)
    except StripeError:
        logger.warning("Stripe test webhook synchronization failed")
        return HttpResponse(status=503)
    return HttpResponse(status=204)
