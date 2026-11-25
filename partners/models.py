from urllib.parse import urlencode
from uuid import uuid4

from django.conf import settings
from django.core.validators import RegexValidator, URLValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from modelcluster.fields import ParentalManyToManyField
from modelcluster.models import ClusterableModel
from wagtail.models import DraftStateMixin, LockableMixin, PreviewableMixin, RevisionMixin, WorkflowMixin


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


class PartnerApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(PartnerAccount, on_delete=models.PROTECT, related_name="applications")
    listing = models.OneToOneField(BusinessListing, on_delete=models.PROTECT, related_name="application")
    checkout_attempt = models.UUIDField(default=uuid4, editable=False)
    checkout_plan = models.CharField(max_length=8, blank=True)
    checkout_id = models.CharField(max_length=255, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    billing_status = models.CharField(max_length=30, blank=True)
    paid_until = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    BILLABLE_STATUSES = ("active", "past_due")
    ENDED_STATUSES = ("canceled", "incomplete_expired")

    @cached_property
    def approved(self):
        return self.listing.live and self.listing.stops.filter(tour__is_published=True).exists()

    @property
    def is_paid(self):
        return (
            self.billing_status in self.BILLABLE_STATUSES
            and self.paid_until is not None
            and self.paid_until > timezone.now()
        )

    @property
    def can_checkout(self):
        return self.approved and (not self.stripe_subscription_id or self.billing_status in self.ENDED_STATUSES)


def published_placements(tour=None):
    placements = RoutePlacement.objects.filter(
        Q(listing__requires_subscription=False) | Q(
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
