from django import forms
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, ObjectList
from wagtail.admin.ui.tables import Column, LiveStatusTagColumn
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import IndexView, SnippetViewSet

from siteapp.models import TourStop

from .activity import with_recent_activity
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

    def clean_stops(self):
        stops = self.cleaned_data["stops"]
        if self.instance.requires_subscription and len({stop.tour_id for stop in stops}) > 1:
            raise forms.ValidationError("A subscription covers one route. Choose stops on the same route.")
        return stops


class BusinessListingIndexView(IndexView):
    def get_queryset(self):
        return with_recent_activity(super().get_queryset())


class BusinessListingViewSet(SnippetViewSet):
    model = BusinessListing
    menu_label = "Business listings"
    menu_order = 235
    icon = "tag"
    add_to_admin_menu = True
    url_namespace = "ea600_business_listings"
    url_prefix = "business-listings"
    index_view_class = BusinessListingIndexView
    list_display = (
        "name", "category", LiveStatusTagColumn(),
        Column("website_clicks", label="Website clicks · 30 days"),
        Column("booking_clicks", label="Booking clicks · 30 days"),
        Column("directions_clicks", label="Directions clicks · 30 days"),
    )
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
        FieldPanel("requires_subscription", read_only=True, heading="Requires subscription"),
        FieldPanel("demo_key", read_only=True, heading="Pilot test business"),
    ], base_form_class=BusinessListingForm)


register_snippet(BusinessListingViewSet)
