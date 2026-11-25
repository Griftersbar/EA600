from pathlib import Path

from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_safe

from partners.models import published_placements

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


def route_content(tour, *, stops=None, days=None):
    if stops is None:
        stops = list(tour.stops.all()) if tour else []
    if days is None:
        days = tour.days.select_related("photo") if tour else []
    track = tour.route_track if tour else []
    geographic_stops = [
        {"number": number, "title": stop.title, "position": [float(stop.latitude), float(stop.longitude)]}
        for number, stop in enumerate(stops, start=1) if stop.has_geographic_position
    ]
    geographic_map = {"track": track, "stops": geographic_stops} if track or geographic_stops else None
    return {
        "tour": tour,
        "stops": stops,
        "geographic_map": geographic_map,
        "show_map": bool(tour and tour.map_image and any(stop.has_map_position for stop in stops)),
        "days": days,
    }


def home(request):
    homepage = homepage_content()
    featured_tour = homepage.featured_tour if homepage else None
    if featured_tour and not featured_tour.is_published:
        featured_tour = None

    tours = published_tours()
    route_slug = request.GET.get("route")
    selected_tour = tours.filter(slug=route_slug).first() if route_slug else None
    tour = selected_tour or featured_tour or tours.first()

    return render(request, "siteapp/home.html", {
        "homepage": homepage,
        "is_home": True,
        **route_content(tour),
        "has_route_listings": bool(tour and published_placements(tour).exists()),
        "route_choices": tours.values_list("slug", "title"),
        "use_tour_copy": tour is not None and tour != featured_tour,
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
        "homepage": homepage_content(), "page": page, "page_title": "Explore routes · EA600",
    })


def tour_detail(request, slug):
    tour = get_object_or_404(published_tours().prefetch_related("gallery"), slug=slug)
    return render_tour_detail(request, tour)


def render_tour_detail(request, tour, *, stops=None, days=None, photos=None, builder_preview=False):
    response = render(request, "siteapp/tour_detail.html", {
        "homepage": homepage_content(),
        "page_title": f"{tour.title} · EA600",
        "photos": tour.gallery.all() if photos is None else photos,
        "builder_preview": builder_preview,
        "placements": () if builder_preview else published_placements(tour),
        **route_content(tour, stops=stops, days=days),
    })
    if builder_preview:
        response.headers["X-Robots-Tag"] = "noindex"
    return response


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
