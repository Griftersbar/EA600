import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from wagtail.signals import published

from .access_tokens import digest
from .mail import email_ready, email_url, send_partner_mail
from .models import BusinessListing, PartnerApplication, PendingPartnerApplication, published_placements


logger = logging.getLogger(__name__)


def deliver_notice(subject, body, email):
    try:
        return bool(send_partner_mail(subject, body, email))
    except OSError:
        logger.warning("Could not deliver EA600 advertiser email")
        return False


def notify_application_received(application):
    deliver_notice(
        "We received your EA600 listing application",
        f"We’ve received your listing for {application.listing.name}. We’ll email you after review "
        "with the next step. You can check its status in My business listings.\n\n"
        + email_url(reverse("partners:advertise", fragment="business-listing-access")),
        application.owner.email,
    )


def email_payment_link(application):
    if not settings.PARTNER_APPLICATIONS_ENABLED or not email_ready() or not application.can_checkout:
        return False
    token = secrets.token_urlsafe(32)
    token_digest = digest(token)
    applications = PartnerApplication.objects.filter(pk=application.pk)
    applications.update(payment_digest=token_digest, payment_link_expires=timezone.now() + timedelta(days=2))
    if deliver_notice(
        "Your EA600 business listing is approved",
        f"Your listing for {application.listing.name} is approved. Open your private link to choose a plan. "
        "The link expires after 48 hours. Your advert will appear once payment is confirmed.\n\n"
        + email_url(reverse("partners:approve_access", args=[token])),
        application.owner.email,
    ):
        return True
    applications.filter(payment_digest=token_digest).update(
        payment_digest=application.payment_digest,
        payment_link_expires=application.payment_link_expires,
    )
    return False


def notify_listing_live(application_id):
    if not settings.PARTNER_APPLICATIONS_ENABLED or not email_ready():
        return
    application = PartnerApplication.objects.select_related("listing", "owner").filter(pk=application_id).first()
    if not application or not application.is_paid or application.live_email_mode == application.billing_mode:
        return
    placements = list(published_placements().filter(listing_id=application.listing_id).select_related(
        "stop__tour", "stop__destination",
    ))
    if not placements:
        return

    applications = PartnerApplication.objects.filter(pk=application.pk, billing_mode=application.billing_mode)
    if not applications.exclude(live_email_mode=application.billing_mode).update(live_email_mode=application.billing_mode):
        return
    links = {}
    for placement in placements:
        stop = placement.stop
        links[email_url(stop.tour.get_absolute_url() + "#places-along-the-route")] = stop.tour.title
        if stop.destination:
            links[email_url(stop.destination.get_absolute_url() + "#destination-businesses")] = stop.destination.title
    pages = "\n".join(f"{title}\n{url}" for url, title in links.items())
    preview = " on the test preview" if application.billing_mode == PartnerApplication.BillingMode.TEST else ""
    if not deliver_notice(
        f"Your EA600 business listing is live{preview}",
        f"Your listing for {application.listing.name} is live{preview}. View your advert here.\n\n{pages}\n\n"
        "Manage your advert and billing in My business listings.\n"
        + email_url(reverse("partners:advertise", fragment="business-listing-access")),
        application.owner.email,
    ):
        applications.filter(live_email_mode=application.billing_mode).update(live_email_mode=application.live_email_mode)


@receiver(published, sender=BusinessListing)
def notify_first_approval(sender, instance, **kwargs):
    if not instance.requires_subscription or not settings.PARTNER_APPLICATIONS_ENABLED or not email_ready():
        return
    application = PartnerApplication.objects.filter(listing=instance).select_related("owner", "listing").first()
    if not application or not application.approved:
        return

    if application.is_paid:
        transaction.on_commit(lambda: notify_listing_live(application.pk))
    elif instance.first_published_at == instance.last_published_at:
        transaction.on_commit(lambda: email_payment_link(application))


@receiver(post_delete, sender=PendingPartnerApplication)
def delete_pending_photo(sender, instance, using, **kwargs):
    if instance.photo:
        transaction.on_commit(lambda: instance.photo.delete(save=False), using=using, robust=True)
