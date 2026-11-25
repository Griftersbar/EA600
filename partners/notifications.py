import logging

from django.conf import settings
from django.db import transaction
from django.dispatch import receiver
from django.urls import reverse
from wagtail.signals import published

from .mail import email_ready, send_partner_mail
from .models import BusinessListing, PartnerApplication


logger = logging.getLogger(__name__)


@receiver(published, sender=BusinessListing)
def notify_first_approval(sender, instance, **kwargs):
    if (not instance.requires_subscription or not settings.PARTNER_APPLICATIONS_ENABLED or not email_ready()
            or instance.first_published_at != instance.last_published_at):
        return
    application = PartnerApplication.objects.filter(listing=instance).select_related("owner", "listing").first()
    if not application or not application.approved:
        return

    def notify():
        url = settings.WAGTAILADMIN_BASE_URL.rstrip("/") + reverse("partners:advertise")
        name = application.listing.name
        try:
            send_partner_mail(
                "Your EA600 business listing is approved",
                f"Your listing for {name} is approved. Sign in with this email to choose a payment plan. "
                f"Your listing will appear on the route once Stripe confirms payment.\n\n{url}",
                application.owner.email,
            )
        except OSError:
            logger.warning("Could not send EA600 listing approval email")

    transaction.on_commit(notify)
