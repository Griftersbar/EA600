from django import forms
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, ObjectList
from wagtail.admin.ui.tables import LiveStatusTagColumn
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from siteapp.models import TourStop

from .models import BusinessListing


class RouteStopChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, stop):
        draft = " (draft route)" if not stop.tour.is_published else ""
        return f"{stop.tour.title}{draft} — {stop.title}"


class BusinessListingForm(WagtailAdminModelForm):
    stops = RouteStopChoiceField(
        queryset=TourStop.objects.select_related("tour").order_by("tour__position", "tour_id", "position", "pk"),
        widget=forms.CheckboxSelectMultiple,
        label="Route stops",
        help_text="Choose the nearest stop on each relevant route.",
    )


class BusinessListingViewSet(SnippetViewSet):
    model = BusinessListing
    menu_label = "Business listings"
    menu_order = 235
    icon = "tag"
    add_to_admin_menu = True
    url_namespace = "ea600_business_listings"
    url_prefix = "business-listings"
    list_display = ("name", "category", LiveStatusTagColumn())
    list_filter = ("category", "live")
    search_fields = ("name", "address")
    search_backend_name = None
    edit_handler = ObjectList([
        FieldPanel("name"),
        FieldPanel("category"),
        FieldPanel("description", widget=forms.Textarea(attrs={"rows": 3})),
        FieldPanel("address"),
        FieldPanel("photo"),
        MultiFieldPanel([FieldPanel("link"), FieldPanel("link_label"), FieldPanel("phone")], heading="Visitor links"),
        FieldPanel("stops"),
    ], base_form_class=BusinessListingForm)


register_snippet(BusinessListingViewSet)
