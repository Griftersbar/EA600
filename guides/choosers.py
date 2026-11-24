from django import forms
from wagtail.admin.forms.choosers import BaseFilterForm
from wagtail.admin.views.generic import chooser as chooser_views
from wagtail.admin.viewsets.chooser import ChooserViewSet
from wagtail.admin.widgets import BaseChooser
from wagtail.images.widgets import AdminImageChooser, ImageChooserAdapter

from siteapp.forms import PhotoForm
from siteapp.models import Tour


class TitleFilterForm(BaseFilterForm):
    q = forms.CharField(label="Search", required=False)

    def filter(self, objects):
        self.search_query = self.cleaned_data["q"]
        self.is_searching = bool(self.search_query)
        return objects.filter(title__icontains=self.search_query) if self.is_searching else objects


class ContentChooserViewSet(ChooserViewSet):
    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(filter_form_class=TitleFilterForm, **kwargs)


class TourChooserViewSet(ContentChooserViewSet):
    model = "siteapp.Tour"
    icon = "site"
    choose_one_text = "Choose a published tour"
    choose_another_text = "Choose another tour"

    def get_object_list(self):
        return Tour.objects.filter(is_published=True)


def photo_preview_data(photo):
    return {
        "preview": {"url": photo.url, "width": 165, "height": 125},
        "default_alt_text": photo.alt_text,
    }


class PhotoChooserWidget(BaseChooser):
    template_name = AdminImageChooser.template_name
    classname = AdminImageChooser.classname
    js_constructor = AdminImageChooser.js_constructor
    media = AdminImageChooser.media

    def get_value_data_from_instance(self, instance):
        return {**super().get_value_data_from_instance(instance), **photo_preview_data(instance)}

    def get_context(self, name, value_data, attrs):
        context = super().get_context(name, value_data, attrs)
        context["preview"] = value_data.get("preview", {})
        context["default_alt_text"] = value_data.get("default_alt_text", "")
        return context


class PhotoChosenResponseMixin:
    def get_chosen_response_data(self, item):
        return {**super().get_chosen_response_data(item), **photo_preview_data(item)}


class PhotoChooseView(chooser_views.ChooseView):
    creation_tab_id = "upload"


class PhotoChosenView(PhotoChosenResponseMixin, chooser_views.ChosenView):
    pass


class PhotoChosenMultipleView(PhotoChosenResponseMixin, chooser_views.ChosenMultipleView):
    pass


class PhotoCreateView(PhotoChosenResponseMixin, chooser_views.CreateView):
    creation_tab_id = "upload"


class PhotoChooserViewSet(ContentChooserViewSet):
    model = "siteapp.Photo"
    icon = "image"
    choose_one_text = "Choose a photo"
    choose_another_text = "Choose another photo"
    creation_form_class = PhotoForm
    creation_tab_label = "Upload a photo"
    create_action_label = "Upload"
    choose_view_class = PhotoChooseView
    chosen_view_class = PhotoChosenView
    chosen_multiple_view_class = PhotoChosenMultipleView
    create_view_class = PhotoCreateView
    base_widget_class = PhotoChooserWidget
    widget_telepath_adapter_class = ImageChooserAdapter


tour_chooser = TourChooserViewSet("guide-tour-chooser")
photo_chooser = PhotoChooserViewSet("guide-photo-chooser")

TourChooserBlock = tour_chooser.get_block_class(module_path=__name__)
PhotoChooserBlock = photo_chooser.get_block_class(module_path=__name__)
