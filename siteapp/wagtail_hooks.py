from django.urls import reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.panels import FieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .builder_views import can_use_builder
from .models import Destination


class DestinationViewSet(SnippetViewSet):
    model = Destination
    icon = "site"
    menu_label = "Destinations"
    add_to_admin_menu = True
    url_namespace = "ea600_destinations"
    url_prefix = "destinations"
    list_display = ("title", "region", "position")
    search_fields = ("title", "region")
    search_backend_name = None
    panels = [
        FieldPanel("title"),
        FieldPanel("region"),
        FieldPanel("description"),
        FieldPanel("photo"),
        FieldPanel("link"),
        FieldPanel("position"),
    ]


register_snippet(DestinationViewSet)


class TourBuilderMenuItem(MenuItem):
    def is_shown(self, request):
        return can_use_builder(request.user)


@hooks.register("register_admin_menu_item")
def register_tour_builder_menu():
    return TourBuilderMenuItem("Tour Builder", reverse("builder_index"), icon_name="site", order=250)
