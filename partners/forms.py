from django import forms

from siteapp.forms import PhotoForm
from siteapp.models import TourStop

from .models import BusinessListing


class OwnerEmailForm(forms.Form):
    email = forms.EmailField(label="Business email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    def clean_email(self):
        return self.cleaned_data["email"].casefold()


class PublishedStopField(forms.ModelChoiceField):
    def label_from_instance(self, stop):
        return f"{stop.tour.title} · {stop.title}"


class PartnerApplicationForm(forms.ModelForm):
    stop = PublishedStopField(
        queryset=TourStop.objects.filter(tour__is_published=True).select_related("tour").order_by(
            "tour__position", "tour_id", "position", "pk",
        ), label="Nearest route stop",
    )
    photo_upload = forms.FileField(required=False, label="Business photo", help_text="JPEG, PNG, WebP or GIF, up to 10 MB.")

    class Meta:
        model = BusinessListing
        fields = ("name", "category", "description", "address", "stop", "link", "link_label", "phone", "photo_upload")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_photo_upload(self):
        upload = self.cleaned_data["photo_upload"]
        if upload:
            photo_form = PhotoForm({"title": self.cleaned_data.get("name") or "Business photo"}, {"image": upload})
            if not photo_form.is_valid():
                raise forms.ValidationError(photo_form.errors["image"])
            return photo_form
