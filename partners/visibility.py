from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from siteapp.models import TourStop
from siteapp.views import render_destination

from .models import BusinessListing, published_placements


def listing_for_editor(request, pk):
    if not request.user.has_perm("partners.change_businesslisting") or not request.user.is_verified():
        raise PermissionDenied
    return get_object_or_404(BusinessListing.objects.select_related("application"), pk=pk)


def preview_destinations(listing):
    # Resolve the placements from the saved revision, including edits to a live listing.
    stops = TourStop.objects.filter(
        pk__in=listing.stops.values_list("id", flat=True),
        tour__is_published=True,
        destination__isnull=False,
    ).select_related("destination")
    return {stop.destination_id: stop.destination for stop in stops}


def visibility_message(listing, stops, public_placements):
    if public_placements:
        return "This advert is visible on its published route stops."
    if not stops:
        return "Choose a route stop in the listing editor and save the listing."
    if not listing.live:
        return "Publish this listing in Wagtail to make it eligible to appear."
    if not any(stop.tour.is_published for stop in stops):
        return "Publish one of the assigned routes to make this listing eligible to appear."
    if listing.demo_key and not settings.PARTNER_PILOT_PREVIEW:
        return "Pilot adverts are hidden on this site."
    application = getattr(listing, "application", None)
    if not application:
        return "This paid listing needs a linked advertiser account."
    if not application.has_current_billing_mode:
        return "This listing needs payment in the site's current billing mode."
    return "Stripe needs to confirm an active paid subscription before this advert appears."


@never_cache
@require_safe
def listing_visibility(request, pk):
    listing = listing_for_editor(request, pk)
    stops = list(listing.stops.select_related("tour"))
    public_placements = list(published_placements().filter(listing=listing).select_related("stop__destination"))
    public_destinations = {
        placement.stop.destination_id: placement.stop.destination
        for placement in public_placements if placement.stop.destination_id
    }
    previews = preview_destinations(listing.get_latest_revision_as_object())
    return render(request, "partners/admin/listing_visibility.html", {
        "listing": listing,
        "listing_url": reverse("ea600_business_listings:edit", args=[listing.pk]),
        "payments_url": reverse("ea600_business_listings:sandbox_payment", args=[listing.pk]),
        "visibility_message": visibility_message(listing, stops, public_placements),
        "public_destinations": public_destinations.values(),
        "missing_destination_links": any(placement.stop.destination_id is None for placement in public_placements),
        "preview_links": [
            (destination, reverse("ea600_business_listings:destination_preview", args=[listing.pk, destination.pk]))
            for destination in previews.values()
        ],
    })


@never_cache
@require_safe
def destination_preview(request, pk, destination_id):
    listing = listing_for_editor(request, pk).get_latest_revision_as_object()
    destination = preview_destinations(listing).get(destination_id)
    if destination is None:
        raise Http404

    response = render_destination(request, destination, preview_listing=listing)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
