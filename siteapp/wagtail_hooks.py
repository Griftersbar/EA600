from wagtail.admin.panels import FieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

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
