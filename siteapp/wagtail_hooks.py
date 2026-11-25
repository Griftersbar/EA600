from django.urls import reverse
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, TitleFieldPanel
from wagtail.admin.ui.tables import Column
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .builder_views import can_use_builder
from .cms_views import HomepageViewSet, SiteSettingsViewSet, homepage_permissions
from .forms import PhotoForm
from .models import Destination, FAQ, FooterPhoto, Highlight, Photo, PlanningTip, Story


def photo_thumbnail(photo):
    return format_html(
        '<img src="{}" alt="" width="96" height="64" loading="lazy" style="object-fit:contain">',
        photo.url,
    )


class PhotoLibraryViewSet(ModelViewSet):
    model = Photo
    name = "ea600_photos"
    url_prefix = "photos"
    menu_label = "EA600 Photos"
    menu_order = 275
    icon = "image"
    add_to_admin_menu = True
    inspect_view_enabled = True
    inspect_view_fields = ("title", "alt_text")
    list_display = ("title", Column("thumbnail", label="Preview", accessor=photo_thumbnail), "alt_text")
    list_per_page = 20
    search_fields = ("title", "alt_text")
    search_backend_name = None

    def get_form_class(self, for_update=False):
        return PhotoForm

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(delete_url_name=None, **kwargs)

    def get_urlpatterns(self):
        return [pattern for pattern in super().get_urlpatterns() if pattern.name != "delete"]


class EditorialSnippetViewSet(SnippetViewSet):
    search_backend_name = None


class DestinationViewSet(EditorialSnippetViewSet):
    model = Destination
    icon = "site"
    menu_label = "Destinations"
    url_namespace = "ea600_destinations"
    url_prefix = "destinations"
    list_display = ("title", "region", "show_on_homepage", "position")
    list_filter = ("show_on_homepage",)
    search_fields = ("title", "region", "slug")
    panels = [
        TitleFieldPanel("title", targets=["slug"]),
        FieldPanel("slug"),
        FieldPanel("region"),
        FieldPanel("description"),
        FieldPanel("photo", heading="Cover photo"),
        InlinePanel("gallery", heading="Photo gallery", label="Gallery photo"),
        FieldPanel("link", heading="Visitor information link"),
        FieldPanel("show_on_homepage"),
        FieldPanel("position"),
    ]


class PlanningTipViewSet(EditorialSnippetViewSet):
    model = PlanningTip
    icon = "list-ul"
    menu_label = "Planning tips"
    url_prefix = "planning-tips"
    list_display = ("title", "position")
    search_fields = ("title", "description")
    panels = [
        FieldPanel("title"), FieldPanel("description"), FieldPanel("photo"), FieldPanel("icon"),
        FieldPanel("link"), FieldPanel("panel_left"), FieldPanel("position"),
    ]


class StoryViewSet(EditorialSnippetViewSet):
    model = Story
    icon = "doc-full"
    menu_label = "Stories"
    url_prefix = "stories"
    list_display = ("title", "is_published", "position", "date")
    list_filter = ("is_published",)
    search_fields = ("title", "excerpt", "author")
    panels = [
        FieldPanel("title"), FieldPanel("slug"), FieldPanel("category"),
        FieldPanel("excerpt"), FieldPanel("body"), FieldPanel("cover"),
        MultiFieldPanel([
            FieldPanel("author"), FieldPanel("author_photo"), FieldPanel("date"), FieldPanel("reading_time"),
        ], heading="Byline"),
        FieldPanel("position"), FieldPanel("is_published", heading="Published"),
    ]


class FAQViewSet(EditorialSnippetViewSet):
    model = FAQ
    icon = "help"
    menu_label = "FAQs"
    url_prefix = "faqs"
    list_display = ("question", "position")
    search_fields = ("question", "answer")
    panels = [FieldPanel("question"), FieldPanel("answer"), FieldPanel("position")]


class HighlightViewSet(EditorialSnippetViewSet):
    model = Highlight
    icon = "list-ul"
    menu_label = "Highlights"
    url_prefix = "highlights"
    list_display = ("title", "position")
    search_fields = ("title", "description")
    panels = [FieldPanel("title"), FieldPanel("description"), FieldPanel("icon"), FieldPanel("position")]


class FooterPhotoViewSet(EditorialSnippetViewSet):
    model = FooterPhoto
    icon = "image"
    menu_label = "Footer photos"
    url_prefix = "footer-photos"
    list_display = ("photo", "position")
    panels = [FieldPanel("photo"), FieldPanel("link"), FieldPanel("position")]


class ContentMenu(SnippetViewSetGroup):
    menu_label = "Content"
    menu_order = 225
    items = (DestinationViewSet, PlanningTipViewSet, StoryViewSet, FAQViewSet, HighlightViewSet, FooterPhotoViewSet)


register_snippet(ContentMenu)
hooks.register("register_permissions", homepage_permissions)


@hooks.register("register_admin_viewset")
def register_ea600_editors():
    return [HomepageViewSet(), SiteSettingsViewSet(), PhotoLibraryViewSet()]


class TourBuilderMenuItem(MenuItem):
    def is_shown(self, request):
        return can_use_builder(request.user)


@hooks.register("register_admin_menu_item")
def register_tour_builder_menu():
    return TourBuilderMenuItem("Tour Builder", reverse("builder_index"), icon_name="site", order=250)
