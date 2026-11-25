import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from .builder_forms import DayFormSet, StopFormSet, TourBuilderForm
from .forms import PhotoForm
from .models import ItineraryDay, Photo, Tour
from .route_tracks import read_gpx
from .views import render_tour_detail


def can_use_builder(user):
    return user.is_active and user.is_staff and (
        user.has_perm("siteapp.add_tour") or user.has_perm("siteapp.change_tour")
    )


@staff_member_required
@require_POST
@never_cache
def builder_import_gpx(request):
    if not can_use_builder(request.user):
        raise PermissionDenied
    file = request.FILES.get("gpx")
    if not file:
        return JsonResponse({"error": "Choose a GPX file to import."}, status=400)
    try:
        track = read_gpx(file)
    except ValidationError as error:
        return JsonResponse({"error": error.messages[0]}, status=400)
    return JsonResponse({"track": track})


@staff_member_required
@require_safe
@never_cache
def builder_index(request):
    if not can_use_builder(request.user):
        raise PermissionDenied
    can_edit = request.user.has_perm("siteapp.change_tour")
    tours = Tour.objects.select_related("cover") if can_edit else Tour.objects.none()
    query = request.GET.get("q", "").strip()
    state = request.GET.get("status", "")
    if query:
        tours = tours.filter(Q(title__icontains=query) | Q(summary__icontains=query))
    if state in {"draft", "published"}:
        tours = tours.filter(is_published=state == "published")
    return render(request, "siteapp/builder/index.html", {
        "page": Paginator(tours, 12).get_page(request.GET.get("page")),
        "query": query,
        "status": state,
        "page_title": "Tour Builder",
    })


def tour_version(tour):
    if not tour.pk:
        return ""
    data = {
        "tour": model_to_dict(tour, exclude=["gallery"]),
        "photos": list(tour.gallery.order_by("pk").values_list("pk", flat=True)),
        "stops": [model_to_dict(stop) for stop in tour.stops.all()],
        "days": [model_to_dict(day) for day in tour.days.all()],
    }
    payload = json.dumps(data, cls=DjangoJSONEncoder, sort_keys=True)
    return salted_hmac("ea600-tour-builder", payload).hexdigest()


def active_forms(formset):
    return [
        form for form in formset.forms
        if (form.instance.pk or form.has_changed()) and not form.cleaned_data.get("DELETE")
    ]


def check_inline_permissions(user, formset):
    for form in formset.forms:
        if form.cleaned_data.get("DELETE"):
            if not form.instance.pk:
                continue
            action = "delete"
        elif form.has_changed():
            action = "change" if form.instance.pk else "add"
        else:
            continue

        if not user.has_perm(f"siteapp.{action}_{formset.model._meta.model_name}"):
            raise PermissionDenied


def save_ordered_stops(formset):
    for form in formset.deleted_forms:
        if form.instance.pk:
            form.instance.delete()
    expected_order = [form.instance.pk for form in formset.initial_forms if form.instance.pk]
    ordered_forms = formset.ordered_forms
    reordered = [form.instance.pk for form in ordered_forms] != expected_order
    for position, form in enumerate(ordered_forms):
        if form.has_changed() or reordered:
            stop = form.save(commit=False)
            stop.tour = formset.instance
            if reordered:
                stop.position = position
            stop.save()


def save_ordered_days(formset):
    for form in formset.deleted_forms:
        if form.instance.pk:
            form.instance.delete()
    renumbered = [
        form for form in formset.initial_forms
        if form.instance.pk and "number" in form.changed_data
    ]
    if renumbered:
        used = set(formset.instance.days.values_list("number", flat=True))
        used.update(form.cleaned_data["number"] for form in active_forms(formset))
        # Move changed rows aside first so swapping two unique day numbers works.
        free_numbers = (number for number in range(32768) if number not in used)
        for form in renumbered:
            ItineraryDay.objects.filter(pk=form.instance.pk).update(number=next(free_numbers))
    formset.save()


@staff_member_required
@require_http_methods(["GET", "POST"])
@never_cache
@transaction.atomic
def builder_edit(request, pk=None):
    permission = "change" if pk else "add"
    if not request.user.has_perm(f"siteapp.{permission}_tour"):
        raise PermissionDenied
    submitted = request.POST if request.method == "POST" else None
    tours = Tour.objects.select_for_update() if submitted is not None else Tour.objects.all()
    tour = get_object_or_404(tours, pk=pk) if pk else Tour()
    was_published = tour.is_published
    live_url = tour.get_absolute_url() if was_published else ""
    title = tour.title if pk else "New tour"
    version = tour_version(tour)
    form = TourBuilderForm(submitted, instance=tour)
    stops = StopFormSet(submitted, instance=tour)
    days = DayFormSet(submitted, instance=tour)
    response_status = 200

    if submitted is not None:
        action = submitted.get("action")
        if action not in {"preview", "draft", "publish"}:
            return HttpResponseBadRequest("Unknown editor action.")
        valid = [form.is_valid(), stops.is_valid(), days.is_valid()]
        if all(valid):
            if action == "preview":
                ordered_days = sorted(
                    (day.instance for day in active_forms(days)), key=lambda day: day.number,
                )
                return render_tour_detail(
                    request, form.instance,
                    stops=[stop.instance for stop in stops.ordered_forms],
                    days=ordered_days,
                    photos=form.cleaned_data["gallery"],
                    builder_preview=True,
                )
            if pk and not constant_time_compare(submitted.get("version", ""), version):
                form.add_error(None, "This tour was edited elsewhere. Open a fresh copy before saving.")
                response_status = 409
            elif action == "draft" and was_published:
                form.add_error(None, "Use Publish changes to update this live tour.")
            else:
                check_inline_permissions(request.user, stops)
                check_inline_permissions(request.user, days)
                try:
                    with transaction.atomic():
                        tour.is_published = action == "publish"
                        form.save()
                        save_ordered_stops(stops)
                        save_ordered_days(days)
                except IntegrityError:
                    form.add_error(None, "This tour could not be saved. Check the URL slug and day numbers.")
                    response_status = 409
                except OperationalError as error:
                    if "locked" not in str(error).lower():
                        raise
                    form.add_error(None, "Another save is in progress. Try again.")
                    response_status = 409
                else:
                    messages.success(request, "Tour published." if action == "publish" else "Draft saved.")
                    return redirect("builder_edit", pk=tour.pk)
        version = submitted.get("version", "")

    return render(request, "siteapp/builder/edit.html", {
        "page_title": title,
        "live_url": live_url,
        "editing": bool(pk),
        "published": was_published,
        "version": version,
        "form": form,
        "stops": stops,
        "days": days,
        "photo_form": PhotoForm(auto_id="id_upload_%s"),
    }, status=response_status)


@staff_member_required
@require_http_methods(["GET", "POST"])
@never_cache
@transaction.atomic
def builder_lifecycle(request, pk, action):
    deleting = action == "delete"
    permission = "delete" if deleting else "change"
    if not request.user.has_perm(f"siteapp.{permission}_tour"):
        raise PermissionDenied

    confirming = request.method == "POST"
    tours = Tour.objects.select_for_update() if confirming else Tour.objects.all()
    tour = get_object_or_404(tours, pk=pk)
    if not deleting and not tour.is_published:
        return redirect("builder_edit", pk=pk)

    version = tour_version(tour)
    conflict = confirming and not constant_time_compare(request.POST.get("version", ""), version)
    if confirming and not conflict:
        if deleting:
            tour.delete()
            messages.success(request, "Tour deleted.")
            return redirect("builder_index")
        tour.is_published = False
        tour.save(update_fields=["is_published"])
        messages.success(request, "Tour unpublished. It is now a draft.")
        return redirect("builder_edit", pk=pk)

    return render(request, "siteapp/builder/confirm.html", {
        "page_title": "Delete tour" if deleting else "Unpublish tour",
        "tour": tour,
        "deleting": deleting,
        "version": version,
        "conflict": conflict,
    }, status=409 if conflict else 200)


def photo_result(photo):
    return {"id": photo.pk, "title": photo.title, "url": photo.url}


@staff_member_required
@require_http_methods(["GET", "POST"])
@never_cache
def builder_photos(request):
    if not can_use_builder(request.user):
        raise PermissionDenied
    if request.method == "POST":
        if not request.user.has_perm("siteapp.add_photo"):
            raise PermissionDenied
        form = PhotoForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        return JsonResponse({"photo": photo_result(form.save())}, status=201)

    query = request.GET.get("q", "").strip()
    photos = Photo.objects.filter(title__icontains=query)
    page = Paginator(photos, 15).get_page(request.GET.get("page"))
    return JsonResponse({
        "photos": [photo_result(photo) for photo in page],
        "page": page.number,
        "has_previous": page.has_previous(),
        "has_next": page.has_next(),
    })
