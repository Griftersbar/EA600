import json
from pathlib import Path

from django.db import migrations


def load_itineraries(apps, schema_editor):
    database = schema_editor.connection.alias

    def records(model):
        return apps.get_model("siteapp", model).objects.using(database)

    def photo_id(filename):
        return (
            records("Photo").filter(bundled_path=f"assets/images/{filename}")
            .values_list("pk", flat=True).first()
        )

    itineraries = json.loads(Path(__file__).with_name("ea600_itineraries.json").read_text(encoding="utf-8"))
    for itinerary in itineraries:
        slug = itinerary.pop("slug")
        stops = itinerary.pop("stops")
        days = itinerary.pop("days")
        cover_id = photo_id(itinerary.pop("cover"))
        tour, created = records("Tour").get_or_create(
            slug=slug,
            defaults={**itinerary, "cover_id": cover_id, "is_published": True},
        )
        if not created:
            continue
        for position, stop in enumerate(stops):
            records("TourStop").create(tour_id=tour.pk, position=position, **stop)
        for day in days:
            filename = day.pop("photo", None)
            records("ItineraryDay").create(tour_id=tour.pk, photo_id=photo_id(filename) if filename else None, **day)


class Migration(migrations.Migration):
    dependencies = [("siteapp", "0005_itineraryday_description")]
    operations = [migrations.RunPython(load_itineraries, migrations.RunPython.noop)]
