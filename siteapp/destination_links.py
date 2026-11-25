from unicodedata import normalize

from django.utils.text import slugify


def place_key(title, region):
    def normalized(text):
        text = normalize("NFKC", text).casefold().replace("’", "'")
        return " ".join(text.split())

    return normalized(title), normalized(region)


def link_missing_destinations(destinations, published_stops, *, tour_id=None, descriptions=None):
    """Fill empty stop links using querysets, including historical models in migrations."""
    candidates = published_stops.filter(destination__isnull=True)
    if tour_id is not None:
        candidates = candidates.filter(tour_id=tour_id)
    stops = list(candidates.order_by("tour_id", "position", "pk"))
    if not stops:
        return

    # Existing stop assignments take precedence over matching editorial records.
    places = {}
    for title, region, destination_id in published_stops.filter(
        destination__isnull=False,
    ).order_by("pk").values_list("title", "region", "destination_id"):
        places.setdefault(place_key(title, region), destination_id)
    slugs = set()
    for pk, title, region, slug in destinations.order_by("pk").values_list("pk", "title", "region", "slug"):
        places.setdefault(place_key(title, region), pk)
        slugs.add(slug)

    stop_descriptions = {}
    for stop in stops:
        if stop.description.strip():
            stop_descriptions.setdefault(place_key(stop.title, stop.region), stop.description.strip())

    for stop in stops:
        key = place_key(stop.title, stop.region)
        destination_id = places.get(key)
        if destination_id is None:
            base = slugify(stop.title) or "destination"
            slug = base
            if slug in slugs and (region := slugify(stop.region)):
                base = slug = f"{base}-{region}"[:156].rstrip("-")
            suffix = 2
            while slug in slugs:
                slug = f"{base[:156]}-{suffix}"
                suffix += 1
            destination = destinations.create(
                title=stop.title,
                region=stop.region,
                slug=slug,
                description=stop_descriptions.get(key) or (descriptions or {}).get(key, ""),
                show_on_homepage=False,
            )
            destination_id = destination.pk
            places[key] = destination_id
            slugs.add(slug)
        stop.destination_id = destination_id

    published_stops.bulk_update(stops, ["destination"])
