from pathlib import Path

from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_safe

from .models import IMAGE_TYPES, Destination, FAQ, FooterPhoto, Highlight, HomeContent, PlanningTip, Story, Tour


IMAGE_CONTENT_TYPES = {extension: mime_type for extension, (_, mime_type) in IMAGE_TYPES.items()}
IMAGE_CONTENT_TYPES["avif"] = "image/avif"


def homepage_content():
    return HomeContent.objects.select_related(
        "featured_tour__map_image", "hero_photo", "logo", "badge_logo", "intro_map", "intro_photo_one",
        "intro_photo_two", "intro_photo_three", "faq_photo", "footer_photo", "cta_photo",
    ).first()


def published_tours():
    return Tour.objects.filter(is_published=True).select_related("cover", "map_image")


def route_content(tour):
    stops = list(tour.stops.all()) if tour else []
    return {
        "tour": tour,
        "stops": stops,
        "show_map": bool(tour and tour.map_image and any(stop.has_map_position for stop in stops)),
        "days": tour.days.select_related("photo") if tour else [],
    }


def home(request):
    homepage = homepage_content()
    tour = homepage.featured_tour if homepage else None
    tours = published_tours()
    if not tour or not tour.is_published:
        tour = tours.first()

    return render(request, "siteapp/home.html", {
        "homepage": homepage,
        "is_home": True,
        **route_content(tour),
        "tours": tours[:3],
        "highlights": Highlight.objects.select_related("icon"),
        "destinations": Destination.objects.select_related("photo"),
        "planning_tips": PlanningTip.objects.select_related("photo", "icon"),
        "stories": Story.objects.filter(is_published=True).select_related("cover", "author_photo"),
        "questions": FAQ.objects.all(),
        "footer_photos": FooterPhoto.objects.select_related("photo"),
    })


def tour_list(request):
    page = Paginator(published_tours(), 12).get_page(request.GET.get("page"))
    return render(request, "siteapp/tour_list.html", {
        "homepage": homepage_content(), "page": page, "page_title": "Tours · EA600",
    })


def tour_detail(request, slug):
    tour = get_object_or_404(published_tours().prefetch_related("gallery"), slug=slug)
    return render(request, "siteapp/tour_detail.html", {
        "homepage": homepage_content(), "page_title": f"{tour.title} · EA600", **route_content(tour),
    })


def story_detail(request, slug):
    story = get_object_or_404(Story.objects.filter(is_published=True).select_related("cover"), slug=slug)
    return render(request, "siteapp/story_detail.html", {
        "homepage": homepage_content(), "story": story, "page_title": f"{story.title} · EA600",
    })


@require_safe
def legacy_static(request, name):
    return redirect(static(name), permanent=True)


@require_safe
def photo_file(request, name):
    extension = Path(name).suffix.lower().lstrip(".")
    try:
        file = default_storage.open(name, "rb")
    except FileNotFoundError as error:
        raise Http404("Photo not found.") from error
    return FileResponse(file, content_type=IMAGE_CONTENT_TYPES[extension], headers={"Cache-Control": "public, max-age=86400"})
