from django import forms
from wagtail.admin.forms.choosers import BaseFilterForm
from wagtail.admin.viewsets.chooser import ChooserViewSet

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


tour_chooser = TourChooserViewSet("guide-tour-chooser")
photo_chooser = ContentChooserViewSet(
    "guide-photo-chooser",
    model="siteapp.Photo",
    icon="image",
    choose_one_text="Choose a photo",
    choose_another_text="Choose another photo",
    creation_form_class=PhotoForm,
    creation_tab_label="Upload a photo",
    create_action_label="Upload",
)

TourChooserBlock = tour_chooser.get_block_class(module_path=__name__)
PhotoChooserBlock = photo_chooser.get_block_class(module_path=__name__)
