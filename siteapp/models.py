from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse


IMAGE_TYPES = {
    "jpg": ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "png": ("PNG", "image/png"),
    "webp": ("WEBP", "image/webp"),
    "gif": ("GIF", "image/gif"),
}


def photo_path(instance, filename):
    return f"photos/{uuid4().hex}{Path(filename).suffix.lower()}"


def validate_photo_size(file):
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("Upload an image no larger than 10 MB.")


class Photo(models.Model):
    title = models.CharField(max_length=140)
    alt_text = models.CharField(max_length=250, blank=True)
    image = models.ImageField(
        upload_to=photo_path,
        blank=True,
        validators=[FileExtensionValidator(IMAGE_TYPES), validate_photo_size],
        help_text="JPEG, PNG, WebP or GIF, up to 10 MB.",
    )
    bundled_path = models.CharField(max_length=200, blank=True, editable=False)

    class Meta:
        ordering = ["title", "pk"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if not self.image and not self.bundled_path:
            raise ValidationError({"image": "Choose a photo to upload."})

    @property
    def url(self):
        return self.image.url if self.image else static(self.bundled_path)


class OrderedContent(models.Model):
    position = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first.")

    class Meta:
        abstract = True
        ordering = ["position", "pk"]


class Tour(OrderedContent):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True, help_text="Part of the public URL. Keep it stable once published.")
    summary = models.TextField(help_text="Short introduction for the tour list.")
    description = models.TextField(blank=True)
    region = models.CharField(max_length=120, blank=True, help_text="Shown on route cards.")
    cover = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    map_image = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    gallery = models.ManyToManyField(Photo, blank=True, related_name="+")
    distance_miles = models.PositiveIntegerField(null=True, blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    counties = models.PositiveIntegerField(null=True, blank=True)
    start_finish = models.CharField(max_length=120, blank=True)
    best_season = models.CharField(max_length=100, blank=True)
    road_types = models.CharField(max_length=140, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("tour_detail", args=[self.slug])


class TourStop(OrderedContent):
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="stops")
    title = models.CharField(max_length=140)
    region = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    day_number = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    onward_journey = models.CharField(max_length=160, blank=True, help_text="For example, 30 miles · 40m to Ely.")
    map_x = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage across the map from the left.",
    )
    map_y = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage down the map from the top.",
    )
    guide_points = models.JSONField(default=list, editable=False, blank=True)

    def clean(self):
        super().clean()
        if (self.map_x is None) != (self.map_y is None):
            raise ValidationError("Enter both map positions or leave both blank.")

    @property
    def has_map_position(self):
        return self.map_x is not None and self.map_y is not None

    def __str__(self):
        return self.title


class ItineraryDay(models.Model):
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="days")
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    title = models.CharField(max_length=140)
    route = models.CharField(max_length=200, blank=True)
    distance = models.CharField(max_length=60, blank=True)
    driving_time = models.CharField(max_length=60, blank=True)
    overnight = models.CharField(max_length=100, blank=True)
    tip = models.TextField(blank=True)
    highlights = models.TextField(blank=True, help_text="Enter one highlight per line.")
    photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["number", "pk"]
        constraints = [models.UniqueConstraint(fields=["tour", "number"], name="unique_tour_day")]

    @property
    def highlight_list(self):
        return [line.strip() for line in self.highlights.splitlines() if line.strip()]

    def __str__(self):
        return f"Day {self.number} · {self.title}"


class HomeContent(models.Model):
    site_title = models.CharField(max_length=200)
    featured_tour = models.ForeignKey(Tour, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    hero_title = models.CharField(max_length=100)
    hero_eyebrow = models.CharField(max_length=160)
    hero_description = models.TextField()
    hero_quote = models.CharField(max_length=200, blank=True)
    hero_route_label = models.CharField(max_length=60)
    hero_itinerary_label = models.CharField(max_length=60)
    hero_photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    logo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    badge_logo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    intro_title = models.CharField(max_length=160)
    intro_description = models.TextField()
    intro_map = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    intro_photo_one = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    intro_photo_two = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    intro_photo_three = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    route_title = models.CharField(max_length=160)
    route_subtitle = models.CharField(max_length=160, blank=True)
    route_description = models.TextField(blank=True)
    destinations_title = models.CharField(max_length=160)
    destinations_description = models.TextField(blank=True)
    itinerary_title = models.CharField(max_length=160)
    itinerary_subtitle = models.CharField(max_length=160, blank=True)
    itinerary_description = models.TextField(blank=True)
    planning_title = models.CharField(max_length=160)
    planning_subtitle = models.CharField(max_length=160, blank=True)
    planning_description = models.TextField(blank=True)
    stories_title = models.CharField(max_length=160)
    stories_subtitle = models.CharField(max_length=160, blank=True)
    faq_title = models.CharField(max_length=160)
    faq_photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    footer_photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cta_title = models.CharField("call to action title", max_length=160)
    cta_subtitle = models.CharField("call to action subtitle", max_length=160, blank=True)
    cta_description = models.TextField("call to action text", blank=True)
    cta_button = models.CharField("call to action button", max_length=60)
    cta_photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    footer_tagline = models.CharField(max_length=200, blank=True)
    footer_legal = models.CharField(max_length=220, blank=True)
    footer_motto = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_region = models.CharField(max_length=140, blank=True)
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)

    class Meta:
        verbose_name = "homepage content"
        verbose_name_plural = "homepage content"

    def __str__(self):
        return "EA600 homepage"


class Highlight(OrderedContent):
    title = models.CharField(max_length=120)
    description = models.TextField()
    icon = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return self.title


class Destination(OrderedContent):
    title = models.CharField(max_length=140)
    region = models.CharField(max_length=100)
    description = models.TextField()
    photo = models.ForeignKey(Photo, on_delete=models.PROTECT, related_name="+")
    link = models.URLField(blank=True)

    def __str__(self):
        return self.title


class PlanningTip(OrderedContent):
    title = models.CharField(max_length=140)
    description = models.TextField()
    photo = models.ForeignKey(Photo, on_delete=models.PROTECT, related_name="+")
    icon = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    link = models.URLField(blank=True)
    panel_left = models.BooleanField("text panel on the left", default=False)

    def __str__(self):
        return self.title


class Story(OrderedContent):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True)
    category = models.CharField(max_length=80, blank=True)
    excerpt = models.TextField()
    body = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    author = models.CharField(max_length=100, blank=True)
    author_photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cover = models.ForeignKey(Photo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reading_time = models.CharField(max_length=40, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)

    def get_absolute_url(self):
        return reverse("story_detail", args=[self.slug])

    def __str__(self):
        return self.title


class FAQ(OrderedContent):
    question = models.CharField(max_length=200)
    answer = models.TextField()

    class Meta(OrderedContent.Meta):
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class FooterPhoto(OrderedContent):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="+")
    link = models.URLField(blank=True)

    def __str__(self):
        return str(self.photo)
