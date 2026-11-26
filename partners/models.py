from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator, URLValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from modelcluster.fields import ParentalManyToManyField
from modelcluster.models import ClusterableModel
from wagtail.contrib.settings.models import BaseGenericSetting
from wagtail.fields import StreamField
from wagtail.models import DraftStateMixin, LockableMixin, PreviewableMixin, RevisionMixin, WorkflowMixin

from .blocks import AdvertiserCardsBlock, AdvertiserNoteBlock, EnquiryFieldsBlock, default_advertiser_sections, default_enquiry_fields


class BusinessListing(WorkflowMixin, LockableMixin, DraftStateMixin, RevisionMixin, PreviewableMixin, ClusterableModel):
    class Category(models.TextChoices):
        FOOD = "food", "Eat & drink"
        STAY = "stay", "Stay"
        SHOP = "shop", "Shop & craft"

    class LinkLabel(models.TextChoices):
        WEBSITE = "website", "Visit website"
        BOOKING = "booking", "Book direct"

    name = models.CharField(max_length=140)
    category = models.CharField(max_length=20, choices=Category)
    description = models.CharField(max_length=320, help_text="A short description for the route page.")
    address = models.CharField(max_length=200, help_text="Include the town and postcode for directions.")
    photo = models.ForeignKey("siteapp.Photo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    link = models.URLField("website or booking link", max_length=500, validators=[URLValidator(schemes=["http", "https"])])
    link_label = models.CharField(max_length=20, choices=LinkLabel, default=LinkLabel.WEBSITE)
    phone = models.CharField(
        max_length=16, blank=True, validators=[RegexValidator(r"\A\+?[0-9]{7,15}\Z", "Enter a phone number without spaces.")],
        help_text="Optional public phone number. Use digits and an optional leading +.",
    )
    stops = ParentalManyToManyField("siteapp.TourStop", through="RoutePlacement", related_name="business_listings")
    live = models.BooleanField(default=False, editable=False)
    requires_subscription = models.BooleanField(default=False, editable=False)
    demo_key = models.SlugField(max_length=64, unique=True, null=True, editable=False)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    def get_preview_template(self, request, mode_name):
        return "partners/preview.html"

    @property
    def link_action(self):
        return ListingClick.Action.BOOKING if self.link_label == self.LinkLabel.BOOKING else ListingClick.Action.WEBSITE

    @property
    def directions_url(self):
        return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": f"{self.name}, {self.address}"})


class RoutePlacement(models.Model):
    listing = models.ForeignKey(BusinessListing, on_delete=models.CASCADE, related_name="placements")
    stop = models.ForeignKey("siteapp.TourStop", on_delete=models.CASCADE, related_name="business_placements")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["listing", "stop"], name="unique_business_listing_stop")]


class ListingClick(models.Model):
    class Action(models.TextChoices):
        WEBSITE = "website", "Website"
        BOOKING = "booking", "Booking"
        DIRECTIONS = "directions", "Directions"

    listing = models.ForeignKey(BusinessListing, on_delete=models.CASCADE, related_name="click_days")
    day = models.DateField()
    action = models.CharField(max_length=12, choices=Action)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["listing", "day", "action"], name="unique_listing_click_day_action")]


class PartnerAccount(models.Model):
    email = models.EmailField(unique=True)
    access_digest = models.CharField(max_length=64, blank=True, db_index=True)
    access_expires = models.DateTimeField(null=True, blank=True)


def pending_photo_path(instance, filename):
    return f"pending_partner_photos/{uuid4().hex}{Path(filename).suffix.lower()}"


class PendingPartnerApplication(models.Model):
    email = models.EmailField()
    verification_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    details = models.JSONField()
    photo = models.FileField(upload_to=pending_photo_path, blank=True)


class AdvertisePageSettings(BaseGenericSetting):
    select_related = ("hero_photo",)

    title = models.CharField(max_length=160, default="Advertise on EA600")
    hero_subtitle = models.CharField(max_length=160, blank=True, default="Reach travellers along the EA600")
    hero_photo = models.ForeignKey("siteapp.Photo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    introduction = models.TextField(
        default="Help road-trippers find your restaurant, tea room, accommodation, shop or workshop as they plan their route.",
    )
    enquiry_link_label = models.CharField(max_length=80, default="Make an enquiry")
    package_heading = models.CharField(max_length=160, default="One business location on one route")
    package_description = models.TextField(default=(
        "Your listing can include a photo, directions, and a link to your website or booking page. "
        "Tell us which stop you’re near. We’ll review your listing before you choose a payment plan."
    ))
    monthly_price = models.DecimalField(
        "Monthly price (£)", max_digits=8, decimal_places=2, default=Decimal("12.00"),
        validators=[MinValueValidator(Decimal("0.30"))],
    )
    annual_price = models.DecimalField(
        "Annual price (£)", max_digits=8, decimal_places=2, default=Decimal("120.00"),
        validators=[MinValueValidator(Decimal("0.30"))],
    )
    show_plan_prices = models.BooleanField(default=True, help_text="Show the monthly and annual prices used by checkout.")
    advertiser_sections = StreamField(
        [("cards", AdvertiserCardsBlock()), ("note", AdvertiserNoteBlock())],
        default=default_advertiser_sections, blank=True, use_json_field=True,
    )
    enquiry_heading = models.CharField(max_length=160, default="Advertising enquiry")
    enquiry_description = models.TextField(default=(
        "Ask about advertising options or where your business could appear. We’ll use your contact details to reply."
    ))
    enquiry_submit_label = models.CharField(max_length=80, default="Send enquiry")
    enquiry_confirmation = models.TextField(default=(
        "Thanks for getting in touch. We’ve received your enquiry and will reply by email."
    ))
    enquiry_fields = StreamField(EnquiryFieldsBlock(), default=default_enquiry_fields, use_json_field=True)
    sign_in_label = models.CharField(max_length=80, default="Email me a sign-in link")
    sign_in_confirmation = models.CharField(max_length=240, default="Check your inbox for a sign-in link. The link is valid for 20 minutes.")
    owner_listings_label = models.CharField(max_length=80, default="Open my listings")
    applications_closed_message = models.CharField(max_length=240, default="Online listing applications are currently closed.")
    pilot_activity_label = models.CharField(max_length=80, default="View pilot test activity")

    class Meta:
        verbose_name = "Advertise page"


class AdvertisingEnquiry(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REPLIED = "replied", "Replied"

    business_name = models.CharField(max_length=140, blank=True)
    contact_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    location = models.CharField(max_length=120, blank=True)
    message = models.TextField(max_length=2000, blank=True)
    additional_answers = models.JSONField(default=list, blank=True, editable=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.NEW)

    class Meta:
        ordering = ["-submitted_at", "-pk"]
        default_permissions = ("view", "change", "delete")
        verbose_name_plural = "advertising enquiries"

    def __str__(self):
        return self.business_name or self.contact_name or self.email

    @property
    def subject(self):
        return str(self)

    @property
    def listing_status(self):
        return "Converted" if hasattr(self, "application") else "—"


class PartnerApplication(models.Model):
    class BillingMode(models.TextChoices):
        TEST = "test", "Test"
        LIVE = "live", "Live"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(PartnerAccount, on_delete=models.PROTECT, related_name="applications")
    listing = models.OneToOneField(BusinessListing, on_delete=models.PROTECT, related_name="application")
    source_enquiry = models.OneToOneField(
        AdvertisingEnquiry, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="application",
    )
    billing_mode = models.CharField(max_length=4, choices=BillingMode, default=BillingMode.TEST, editable=False)
    checkout_attempt = models.UUIDField(default=uuid4, editable=False)
    checkout_plan = models.CharField(max_length=8, blank=True)
    checkout_amount_pence = models.PositiveIntegerField(null=True, blank=True, editable=False)
    checkout_id = models.CharField(max_length=255, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    billing_status = models.CharField(max_length=30, blank=True)
    paid_until = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    payment_digest = models.CharField(max_length=64, blank=True, db_index=True)
    payment_link_expires = models.DateTimeField(null=True, blank=True)
    live_email_mode = models.CharField(max_length=4, choices=BillingMode, blank=True)

    BILLABLE_STATUSES = ("active", "past_due")
    ENDED_STATUSES = ("canceled", "incomplete_expired")

    @cached_property
    def approved(self):
        return self.listing.live and self.listing.stops.filter(tour__is_published=True).exists()

    @property
    def has_current_billing_mode(self):
        return self.billing_mode == settings.PARTNER_BILLING_MODE

    @property
    def is_paid(self):
        return (
            self.has_current_billing_mode
            and self.billing_status in self.BILLABLE_STATUSES
            and self.paid_until is not None
            and self.paid_until > timezone.now()
        )

    @property
    def can_checkout(self):
        if not self.approved:
            return False
        if not self.has_current_billing_mode:
            return self.billing_mode == self.BillingMode.TEST and settings.PARTNER_BILLING_MODE == self.BillingMode.LIVE
        return not self.stripe_subscription_id or self.billing_status in self.ENDED_STATUSES


def published_placements(tour=None):
    placements = RoutePlacement.objects.filter(
        Q(listing__requires_subscription=False) | Q(
            listing__application__billing_mode=settings.PARTNER_BILLING_MODE,
            listing__application__billing_status__in=PartnerApplication.BILLABLE_STATUSES,
            listing__application__paid_until__gt=timezone.now(),
        ),
        stop__tour__is_published=True, listing__live=True,
    ).select_related("stop", "listing__photo").order_by("stop__position", "stop_id", "listing__name", "listing_id")
    if tour is not None:
        placements = placements.filter(stop__tour=tour)
    if not settings.PARTNER_PILOT_PREVIEW:
        placements = placements.filter(listing__demo_key__isnull=True)
    return placements
