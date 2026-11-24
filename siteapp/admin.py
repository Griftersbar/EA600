from django.contrib import admin
from django.utils.html import format_html

from .forms import PhotoForm
from .models import (
    Destination, FAQ, FooterPhoto, Highlight, HomeContent, ItineraryDay,
    Photo, PlanningTip, Story, Tour, TourStop,
)


admin.site.site_header = "EA600 Admin"
admin.site.site_title = "EA600 Admin"
admin.site.index_title = "Manage EA600 content"


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    form = PhotoForm
    list_display = ("title", "thumbnail", "alt_text")
    search_fields = ("title", "alt_text")
    readonly_fields = ("thumbnail",)

    @admin.display(description="Preview")
    def thumbnail(self, photo):
        if photo and (photo.image or photo.bundled_path):
            return format_html(
                '<img src="{}" alt="{}" style="max-width:96px;max-height:64px;object-fit:contain">',
                photo.url, photo.alt_text,
            )
        return "—"


class TourStopInline(admin.StackedInline):
    model = TourStop
    extra = 0
    fields = ("title", "region", "description", "position", "day_number", "onward_journey", ("map_x", "map_y"))


class ItineraryDayInline(admin.StackedInline):
    model = ItineraryDay
    extra = 0
    autocomplete_fields = ("photo",)


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "position", "duration_days", "distance_miles")
    list_filter = ("is_published",)
    list_editable = ("is_published", "position")
    search_fields = ("title", "summary", "slug")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("cover", "map_image", "gallery")
    inlines = (TourStopInline, ItineraryDayInline)


@admin.register(HomeContent)
class HomeContentAdmin(admin.ModelAdmin):
    autocomplete_fields = (
        "featured_tour", "hero_photo", "logo", "badge_logo", "intro_map", "intro_photo_one", "intro_photo_two",
        "intro_photo_three", "faq_photo", "footer_photo", "cta_photo",
    )
    fieldsets = (
        ("Site identity", {"fields": ("site_title", "logo", "badge_logo", "featured_tour")}),
        ("Hero", {"fields": (
            "hero_title", "hero_eyebrow", "hero_description", "hero_quote", "hero_photo", "hero_route_label",
            "hero_itinerary_label",
        )}),
        ("Introduction", {"fields": (
            "intro_title", "intro_description", "intro_map", "intro_photo_one", "intro_photo_two", "intro_photo_three",
        )}),
        ("Route and destinations", {"fields": (
            "route_title", "route_subtitle", "route_description", "destinations_title", "destinations_description",
        )}),
        ("Itinerary and planning", {"fields": (
            "itinerary_title", "itinerary_subtitle", "itinerary_description",
            "planning_title", "planning_subtitle", "planning_description",
        )}),
        ("Stories and questions", {"fields": ("stories_title", "stories_subtitle", "faq_title", "faq_photo")}),
        ("Footer and call to action", {"fields": (
            "footer_photo", "cta_title", "cta_subtitle", "cta_description", "cta_button", "cta_photo", "footer_tagline",
            "footer_legal", "footer_motto", "contact_email", "contact_phone", "contact_region",
            "instagram_url", "facebook_url", "youtube_url",
        )}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HomeContent.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Highlight, Destination, PlanningTip, FAQ, FooterPhoto)
class OrderedContentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "position")

    def get_autocomplete_fields(self, request):
        return tuple(field.name for field in self.model._meta.fields if field.related_model is Photo)


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "position", "date")
    list_filter = ("is_published",)
    search_fields = ("title", "excerpt", "author")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("cover", "author_photo")
