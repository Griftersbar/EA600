from django.core.validators import RegexValidator, URLValidator
from django.db import models
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

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    def get_preview_template(self, request, mode_name):
        return "partners/preview.html"


class RoutePlacement(models.Model):
    listing = models.ForeignKey(BusinessListing, on_delete=models.CASCADE, related_name="placements")
    stop = models.ForeignKey("siteapp.TourStop", on_delete=models.CASCADE, related_name="business_placements")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["listing", "stop"], name="unique_business_listing_stop")]


def published_placements(tour):
    return RoutePlacement.objects.filter(
        stop__tour=tour, stop__tour__is_published=True, listing__live=True,
    ).select_related("stop", "listing__photo").order_by("stop__position", "stop_id", "listing__name", "listing_id")
