from django.core.exceptions import PermissionDenied
from django.db import OperationalError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from wagtail.admin import messages

from .forms import PartnerApplicationForm
from .models import AdvertisingEnquiry, PartnerAccount, PartnerApplication


def can_convert_enquiry(user):
    return user.has_perms(("partners.change_advertisingenquiry", "partners.add_businesslisting"))


def listing_edit_url(user, application):
    if user.has_perm("partners.change_businesslisting"):
        return reverse("ea600_business_listings:edit", args=[application.listing_id])
    return None


def enquiry_listing_action(user, enquiry):
    application = getattr(enquiry, "application", None)
    if application:
        return "Open business listing", listing_edit_url(user, application)
    if can_convert_enquiry(user):
        return "Create business listing", reverse("ea600_advertising_enquiries:convert", args=[enquiry.pk])
    return None, None


def open_created_listing(request, application, enquiry_url):
    return redirect(listing_edit_url(request.user, application) or enquiry_url)


@require_http_methods(["GET", "POST"])
def convert_enquiry(request, pk):
    if not can_convert_enquiry(request.user):
        raise PermissionDenied
    enquiry = get_object_or_404(AdvertisingEnquiry.objects.select_related("application"), pk=pk)
    enquiry_url = reverse("ea600_advertising_enquiries:edit", args=[pk])
    if hasattr(enquiry, "application"):
        return open_created_listing(request, enquiry.application, enquiry_url)

    submitting = request.method == "POST"
    form = PartnerApplicationForm(
        request.POST if submitting else None,
        request.FILES if submitting else None,
        initial={"name": enquiry.business_name, "address": enquiry.location},
    )
    status = 200
    if submitting and form.is_valid():
        try:
            with transaction.atomic():
                source = get_object_or_404(AdvertisingEnquiry.objects.select_for_update(), pk=pk)
                application = PartnerApplication.objects.filter(source_enquiry=source).first()
                if application:
                    return open_created_listing(request, application, enquiry_url)
                owner, _ = PartnerAccount.objects.get_or_create(email=source.email.casefold())
                application = form.create_application(owner, source_enquiry=source, user=request.user)
        except OperationalError as error:
            if "locked" not in str(error).lower():
                raise
            form.add_error(None, "A save is in progress. Try again.")
            status = 409
        else:
            messages.success(request, "Draft business listing created from the enquiry.")
            return open_created_listing(request, application, enquiry_url)

    return render(request, "partners/admin/convert_enquiry.html", {
        "enquiry": enquiry, "enquiry_url": enquiry_url, "form": form,
    }, status=status)
