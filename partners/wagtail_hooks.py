from urllib.parse import quote

from django import forms
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from wagtail import hooks
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, HelpPanel, MultiFieldPanel, ObjectList, Panel, TabbedInterface
from wagtail.admin.ui.tables import Column, LiveStatusTagColumn
from wagtail.admin.views.generic.models import IndexView as ModelIndexView, InspectView
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.admin.widgets.button import HeaderButton
from wagtail.contrib.settings.registry import register_setting
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import EditView, IndexView, SnippetViewSet

from siteapp.models import TourStop

from .activity import with_recent_activity
from .enquiry_conversion import convert_enquiry, enquiry_listing_action
from .models import AdvertisePageSettings, AdvertisingEnquiry, BusinessListing
from .sandbox import advertiser_payments


AdvertisePageSettings.edit_handler = TabbedInterface([
    ObjectList([
        MultiFieldPanel([
            FieldPanel("title"), FieldPanel("hero_subtitle"), FieldPanel("hero_photo"),
            FieldPanel("introduction"), FieldPanel("enquiry_link_label"),
        ], heading="Introduction"),
        MultiFieldPanel([
            FieldPanel("package_heading"), FieldPanel("package_description"),
            HelpPanel(content="New checkouts use these prices. Renewals use each subscription’s agreed price."),
            FieldPanel("monthly_price"), FieldPanel("annual_price"), FieldPanel("show_plan_prices"),
        ], heading="Listing package"),
        FieldPanel("advertiser_sections", heading="Advertiser information"),
        MultiFieldPanel([
            FieldPanel("sign_in_label"), FieldPanel("sign_in_confirmation"), FieldPanel("owner_listings_label"),
            FieldPanel("applications_closed_message"), FieldPanel("pilot_activity_label"),
        ], heading="Business sign-in and pilot links"),
    ], heading="Page content"),
    ObjectList([
        FieldPanel("enquiry_heading"), FieldPanel("enquiry_description"),
        FieldPanel("enquiry_submit_label"), FieldPanel("enquiry_confirmation"),
        FieldPanel("enquiry_fields", help_text="Arrange the fields in display order. Include one reply email field."),
    ], heading="Enquiry form"),
])
register_setting(AdvertisePageSettings, icon="tag")


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


class BusinessListingEditView(EditView):
    def get_header_buttons(self):
        buttons = super().get_header_buttons()
        if self.request.user.has_perm("partners.change_businesslisting"):
            url = reverse("ea600_business_listings:sandbox_payment", args=[self.object.pk])
            buttons.insert(0, HeaderButton("Advertiser payments", url=url, icon_name="tag"))
        return buttons


class BusinessListingViewSet(SnippetViewSet):
    model = BusinessListing
    menu_label = "Business listings"
    menu_order = 235
    icon = "tag"
    add_to_admin_menu = True
    url_namespace = "ea600_business_listings"
    url_prefix = "business-listings"
    index_view_class = BusinessListingIndexView
    edit_view_class = BusinessListingEditView
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

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path("sandbox-payment/<int:pk>/", advertiser_payments, name="sandbox_payment"),
        ]


register_snippet(BusinessListingViewSet)


class EnquiryEmailPanel(FieldPanel):
    def format_value_for_display(self, value):
        return format_html('<a href="mailto:{}">{}</a>', quote(value, safe="@"), value)


def display_enquiry_answers(answers):
    if not answers:
        return "—"
    rows = format_html_join("", "<dt><strong>{}</strong></dt><dd>{}</dd>", (
        (answer["label"], answer["value"] or "—") for answer in answers
    ))
    return format_html("<dl>{}</dl>", rows)


class EnquiryAnswersPanel(FieldPanel):
    def format_value_for_display(self, value):
        return display_enquiry_answers(value)


class AdvertisingEnquiryInspectView(InspectView):
    def get_additional_answers_display_value(self):
        return display_enquiry_answers(self.object.additional_answers)

    def get_header_buttons(self):
        buttons = super().get_header_buttons()
        label, url = enquiry_listing_action(self.request.user, self.object)
        if url:
            buttons.insert(0, HeaderButton(label, url=url, icon_name="tag"))
        return buttons


class EnquiryListingPanel(Panel):
    class BoundPanel(Panel.BoundPanel):
        template_name = "partners/admin/enquiry_listing_panel.html"

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            label, url = enquiry_listing_action(self.request.user, self.instance)
            return {**context, "listing_action_label": label, "listing_action_url": url}


class AdvertisingEnquiryIndexView(ModelIndexView):
    def get_queryset(self):
        return super().get_queryset().select_related("application")


class AdvertisingEnquiryViewSet(ModelViewSet):
    model = AdvertisingEnquiry
    name = "ea600_advertising_enquiries"
    url_prefix = "advertising-enquiries"
    menu_label = "Advertising enquiries"
    menu_order = 236
    add_to_admin_menu = True
    icon = "mail"
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_class = AdvertisingEnquiryInspectView
    index_view_class = AdvertisingEnquiryIndexView
    inspect_view_fields = ("business_name", "contact_name", "email", "location", "message", "additional_answers", "submitted_at", "status")
    list_display = ("subject", "location", "status", Column("listing_status", label="Listing"), "submitted_at")
    list_filter = ("status",)
    search_fields = ("business_name", "location", "email")
    search_backend_name = None
    panels = [
        EnquiryListingPanel(),
        FieldPanel("business_name", read_only=True),
        FieldPanel("contact_name", read_only=True),
        EnquiryEmailPanel("email", read_only=True, heading="Reply by email"),
        FieldPanel("location", read_only=True),
        FieldPanel("message", read_only=True),
        EnquiryAnswersPanel("additional_answers", read_only=True),
        FieldPanel("submitted_at", read_only=True),
        FieldPanel("status"),
    ]

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(add_url_name=None, **kwargs)

    def get_urlpatterns(self):
        return [
            *[pattern for pattern in super().get_urlpatterns() if pattern.name != "add"],
            path("convert/<int:pk>/", convert_enquiry, name="convert"),
        ]


@hooks.register("register_admin_viewset")
def register_advertising_enquiries():
    return AdvertisingEnquiryViewSet()
