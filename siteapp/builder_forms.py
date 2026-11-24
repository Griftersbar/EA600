from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import ItineraryDay, Photo, Tour, TourStop


class PhotoPicker(forms.Widget):
    template_name = "siteapp/builder/photo_picker.html"

    def __init__(self, attrs=None, *, multiple=False):
        super().__init__(attrs)
        self.allow_multiple_selected = multiple

    def value_from_datadict(self, data, files, name):
        if self.allow_multiple_selected and hasattr(data, "getlist"):
            return data.getlist(name)
        return data.get(name)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        raw_values = value if isinstance(value, (list, tuple)) else [value]
        photo_ids = []
        for raw in raw_values:
            try:
                photo_id = int(str(raw))
            except (TypeError, ValueError):
                continue
            if 0 < photo_id < 2**63:
                photo_ids.append(photo_id)
        photos = Photo.objects.in_bulk(photo_ids)
        context["widget"].update(
            multiple=self.allow_multiple_selected,
            photos=[photos[photo_id] for photo_id in photo_ids if photo_id in photos],
        )
        return context


class TourBuilderForm(forms.ModelForm):
    class Meta:
        model = Tour
        fields = (
            "title", "slug", "summary", "description", "cover", "map_image", "gallery",
            "distance_miles", "duration_days", "counties", "start_finish", "best_season", "road_types", "position",
        )
        labels = {"slug": "URL slug", "position": "Catalogue order", "gallery": "Gallery photos"}
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 5}),
            "cover": PhotoPicker(),
            "map_image": PhotoPicker(),
            "gallery": PhotoPicker(multiple=True),
        }


class StopBuilderForm(forms.ModelForm):
    class Meta:
        model = TourStop
        fields = ("title", "region", "description", "day_number", "onward_journey", "map_x", "map_y")
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class DayBuilderForm(forms.ModelForm):
    class Meta:
        model = ItineraryDay
        fields = ("number", "title", "route", "distance", "driving_time", "overnight", "tip", "highlights", "photo")
        labels = {"number": "Day number"}
        widgets = {
            "tip": forms.Textarea(attrs={"rows": 2}),
            "highlights": forms.Textarea(attrs={"rows": 3}),
            "photo": PhotoPicker(),
        }


class OrderedStopFormSet(BaseInlineFormSet):
    ordering_widget = forms.HiddenInput


StopFormSet = inlineformset_factory(Tour, TourStop, StopBuilderForm, formset=OrderedStopFormSet, extra=0, can_order=True)
DayFormSet = inlineformset_factory(Tour, ItineraryDay, DayBuilderForm, extra=0)
