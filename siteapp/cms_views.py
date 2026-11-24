from django import forms
from django.contrib.auth.models import Permission
from django.http import Http404
from django.urls import path, reverse
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.menu import MenuItem
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, ObjectList
from wagtail.admin.views.generic.models import EditView
from wagtail.admin.viewsets.base import ViewSet

from .models import HomeContent


class HomeContentForm(WagtailAdminModelForm):
    def clean_featured_tour(self):
        tour = self.cleaned_data["featured_tour"]
        if tour and not tour.is_published and "featured_tour" in self.changed_data:
            raise forms.ValidationError("Choose a published tour.")
        return tour

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit and self.changed_data:
            # Both editors share the same row. Save only the fields in this form.
            instance.save(update_fields=self.changed_data)
        return instance


class HomeContentEditView(EditView):
    model = HomeContent

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        content = queryset.first()
        if content is None:
            raise Http404("EA600 homepage content is missing.")
        return content

    def get_page_subtitle(self):
        return self.page_title

    def get_edit_url(self):
        return reverse(self.edit_url_name)

    def get_success_url(self):
        return self.get_edit_url()

    def get_success_buttons(self):
        return []


class HomeContentMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.has_perm("siteapp.change_homecontent")


class HomeContentViewSet(ViewSet):
    menu_item_class = HomeContentMenuItem

    def get_urlpatterns(self):
        panel = ObjectList(self.panels, base_form_class=HomeContentForm).bind_to_model(HomeContent)
        view = self.construct_view(
            HomeContentEditView,
            edit_url_name=self.get_url_name("edit"),
            page_title=self.menu_label,
            success_message=self.success_message,
            panel=panel,
        )
        return [path("", view, name="edit")]


class HomepageViewSet(HomeContentViewSet):
    name = "ea600_homepage"
    url_prefix = "homepage"
    menu_label = "Homepage"
    menu_order = 200
    icon = "home"
    add_to_admin_menu = True
    success_message = "Homepage saved."
    panels = [
        FieldPanel("featured_tour", help_text="Choose a published tour to feature on the homepage."),
        MultiFieldPanel([
            FieldPanel("hero_title"), FieldPanel("hero_eyebrow"), FieldPanel("hero_description"),
            FieldPanel("hero_quote"), FieldPanel("hero_photo"), FieldPanel("hero_route_label"),
            FieldPanel("hero_itinerary_label"),
        ], heading="Hero"),
        MultiFieldPanel([
            FieldPanel("intro_title"), FieldPanel("intro_description"), FieldPanel("intro_map"),
            FieldPanel("intro_photo_one"), FieldPanel("intro_photo_two"), FieldPanel("intro_photo_three"),
        ], heading="Introduction"),
        MultiFieldPanel([
            FieldPanel("route_title"), FieldPanel("route_subtitle"), FieldPanel("route_description"),
            FieldPanel("destinations_title"), FieldPanel("destinations_description"),
        ], heading="Route and destinations"),
        MultiFieldPanel([
            FieldPanel("itinerary_title"), FieldPanel("itinerary_subtitle"), FieldPanel("itinerary_description"),
            FieldPanel("planning_title"), FieldPanel("planning_subtitle"), FieldPanel("planning_description"),
        ], heading="Itinerary and planning"),
        MultiFieldPanel([
            FieldPanel("stories_title"), FieldPanel("stories_subtitle"), FieldPanel("faq_title"),
            FieldPanel("faq_photo"),
        ], heading="Stories and questions"),
        MultiFieldPanel([
            FieldPanel("cta_title"), FieldPanel("cta_subtitle"), FieldPanel("cta_description"),
            FieldPanel("cta_button"), FieldPanel("cta_photo"), FieldPanel("footer_photo"),
        ], heading="Call to action and footer images"),
    ]


class SiteSettingsViewSet(HomeContentViewSet):
    name = "ea600_site_settings"
    url_prefix = "site-settings"
    menu_label = "Site settings"
    icon = "cog"
    add_to_settings_menu = True
    menu_order = 50
    success_message = "Site settings saved."
    panels = [
        MultiFieldPanel([
            FieldPanel("site_title"), FieldPanel("logo"), FieldPanel("badge_logo"),
            FieldPanel("footer_tagline"), FieldPanel("footer_motto"), FieldPanel("footer_legal"),
        ], heading="Branding"),
        MultiFieldPanel([
            FieldPanel("contact_email"), FieldPanel("contact_phone"), FieldPanel("contact_region"),
        ], heading="Contact details"),
        MultiFieldPanel([
            FieldPanel("instagram_url"), FieldPanel("facebook_url"), FieldPanel("youtube_url"),
        ], heading="Social links"),
    ]


def homepage_permissions():
    return Permission.objects.filter(content_type__app_label="siteapp", codename="change_homecontent")
