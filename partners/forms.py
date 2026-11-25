from django import forms
from django.core.validators import URLValidator
from django.db import transaction
from django.utils.html import escape

from siteapp.forms import PhotoForm
from siteapp.models import TourStop

from .models import AdvertisingEnquiry, BusinessListing, PartnerApplication


class OwnerEmailForm(forms.Form):
    email = forms.EmailField(label="Business email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    def clean_email(self):
        return self.cleaned_data["email"].casefold()


class AdvertisingEnquiryForm(forms.Form):
    def __init__(self, page, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_fields = []
        widgets = {
            "business_name": forms.TextInput(attrs={"autocomplete": "organization"}),
            "contact_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "message": forms.Textarea(attrs={"rows": 4}),
        }
        for block in page.enquiry_fields:
            kind, value = block.block_type, block.value
            options = {
                "label": value["label"],
                "help_text": escape(value.get("help_text") or ""),
                "required": kind == "reply_email" or bool(value.get("required")),
            }
            if kind in ("standard", "reply_email"):
                name = "email" if kind == "reply_email" else value["field"]
                self.fields[name] = AdvertisingEnquiry._meta.get_field(name).formfield(widget=widgets.get(name), **options)
            else:
                name = f"extra_{block.id}"
                self.fields[name] = self.make_extra_field(kind, value, options)
                self.extra_fields.append(name)

    @staticmethod
    def make_extra_field(kind, value, options):
        if kind == "dropdown":
            choices = [("", "Choose an option")] + [(option, option) for option in value["options"]]
            return forms.ChoiceField(choices=choices, **options)
        if kind == "website":
            return forms.URLField(max_length=500, assume_scheme="https", validators=[URLValidator(schemes=["http", "https"])], **options)
        if kind == "long_text":
            return forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 4}), **options)
        return forms.CharField(max_length=240, **options)

    def save(self):
        answers = self.cleaned_data.copy()
        additional_answers = [
            {"label": self.fields[name].label, "value": answers.pop(name)}
            for name in self.extra_fields
        ]
        return AdvertisingEnquiry.objects.create(additional_answers=additional_answers, **answers)


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

    @transaction.atomic
    def create_application(self, owner, *, source_enquiry=None, user=None):
        listing = self.save(commit=False)
        photo_form = self.cleaned_data["photo_upload"]
        listing.requires_subscription = True
        listing.save()
        if photo_form:
            listing.photo = photo_form.save()
        listing.stops = [self.cleaned_data["stop"]]
        listing.save_revision(user=user)
        # Keep the draft's placement available in the Wagtail listing editor.
        listing.save(update_fields=["stops", "photo"])
        return PartnerApplication.objects.create(listing=listing, owner=owner, source_enquiry=source_enquiry)
