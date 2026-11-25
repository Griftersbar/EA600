from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from partners.models import BusinessListing
from siteapp.models import Photo, TourStop


DEMO_BUSINESSES = (
    ("mile-marker", "Cambridge", "Mile Marker Deli", "food", "Seasonal sandwiches, picnic rolls and deli produce.", "day-01.webp"),
    ("reed-and-linen", "Ely", "Reed & Linen Guesthouse", "stay", "A small guesthouse with breakfast and space to park.", "intro-stack-1.webp"),
    ("quay-thread", "King's Lynn", "Quay Thread Studio", "shop", "Hand-stitched gifts and short workshops for visitors.", ""),
    ("amber-kettle", "Hunstanton", "Amber Kettle Tea Room", "food", "Cream teas, loose-leaf tea and cakes for a coastal stop.", "intro-stack-2.webp"),
    ("tideline-table", "Wells-next-the-Sea", "Tideline Table", "food", "A small restaurant serving a seasonal lunch and dinner menu.", ""),
    ("lantern-cliff", "Cromer", "Lantern Cliff Hotel", "stay", "A coastal hotel with family rooms and breakfast.", "intro-stack-3.webp"),
    ("flint-and-fable", "Norwich", "Flint & Fable Crafts", "shop", "Locally made pottery, prints and small gifts.", ""),
    ("boardwalk-larder", "Great Yarmouth", "Boardwalk Larder", "food", "Coffee, packed lunches and takeaway snacks near the seafront.", "hero-bg.webp"),
    ("sailmakers-rest", "Southwold", "Sailmaker’s Rest B&B", "stay", "Two guest rooms, a cooked breakfast and storage for bikes.", "intro-stack-1.webp"),
    ("shingle-and-ink", "Aldeburgh", "Shingle & Ink Workshop", "shop", "Printmaking demonstrations and coastal stationery.", "intro-stack-3.webp"),
)


class Command(BaseCommand):
    help = "Create ten fictional businesses on the published EA600 route for a pilot preview."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.PARTNER_PILOT_PREVIEW:
            raise CommandError("Enable PARTNER_PILOT_PREVIEW before seeding the test businesses.")
        titles = {business[1] for business in DEMO_BUSINESSES}
        stops = {stop.title: stop for stop in TourStop.objects.filter(tour__slug="ea600", tour__is_published=True, title__in=titles)}
        missing = sorted(titles - stops.keys())
        if missing:
            raise CommandError("The published EA600 route is missing stops: " + ", ".join(missing))

        paths = {f"assets/images/{business[5]}" for business in DEMO_BUSINESSES if business[5]}
        photos = {photo.bundled_path: photo for photo in Photo.objects.filter(bundled_path__in=paths)}
        added = 0
        for key, stop_title, name, category, description, photo_file in DEMO_BUSINESSES:
            listing, created = BusinessListing.objects.get_or_create(demo_key=key, defaults={
                "name": name,
                "category": category,
                "description": description,
                "address": f"{stop_title} · Fictional venue",
                "link": f"https://example.com/{key}",
                "link_label": BusinessListing.LinkLabel.BOOKING if category == "stay" else BusinessListing.LinkLabel.WEBSITE,
                "photo": photos.get(f"assets/images/{photo_file}"),
            })
            if created:
                listing.stops = [stops[stop_title]]
                listing.save_revision().publish()
                added += 1
        self.stdout.write(self.style.SUCCESS(f"Added {added} test businesses. {len(DEMO_BUSINESSES)} pilot fixtures checked."))
