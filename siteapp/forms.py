from pathlib import Path

from django import forms
from django.core.files.uploadedfile import UploadedFile

from .models import IMAGE_TYPES, Photo


class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ("title", "alt_text", "image")

    def clean_image(self):
        image = self.cleaned_data["image"]
        if isinstance(image, UploadedFile):
            extension = Path(image.name).suffix.lower().lstrip(".")
            expected_format = IMAGE_TYPES.get(extension, ("", ""))[0]
            if image.image.format != expected_format:
                raise forms.ValidationError("The file extension must match the image format.")
        return image
