import json
from pathlib import Path

from django.db import migrations


def load_ea600_content(apps, schema_editor):
    database = schema_editor.connection.alias

    def records(model):
        return apps.get_model("siteapp", model).objects.using(database)

    if records("HomeContent").exists():
        return

    data = json.loads(Path(__file__).with_name("ea600_content.json").read_text(encoding="utf-8"))
    photos = {
        path: records("Photo").create(bundled_path=path, **attributes)
        for path, attributes in data["photos"].items()
    }

    def with_photos(attributes, fields):
        return {
            **{key: value for key, value in attributes.items() if key not in fields},
            **{f"{key}_id": photos[attributes[key]].pk for key in fields},
        }

    tour = records("Tour").create(**with_photos(data["tour"], ("cover", "map_image")))
    for stop in data["stops"]:
        records("TourStop").create(tour_id=tour.pk, **stop)
    for day in data["days"]:
        records("ItineraryDay").create(tour_id=tour.pk, **with_photos(day, ("photo",)))

    homepage_photos = (
        "hero_photo", "logo", "badge_logo", "intro_map", "intro_photo_one", "intro_photo_two", "intro_photo_three",
        "faq_photo", "footer_photo", "cta_photo",
    )
    records("HomeContent").create(featured_tour_id=tour.pk, **with_photos(data["homepage"], homepage_photos))

    for model, key, photo_fields in (
        ("Highlight", "highlights", ("icon",)),
        ("Destination", "destinations", ("photo",)),
        ("PlanningTip", "planning_tips", ("photo", "icon")),
        ("Story", "stories", ("cover", "author_photo")),
        ("FAQ", "questions", ()),
        ("FooterPhoto", "footer_photos", ("photo",)),
    ):
        for item in data[key]:
            records(model).create(**with_photos(item, photo_fields))


class Migration(migrations.Migration):
    dependencies = [("siteapp", "0001_initial")]
    operations = [migrations.RunPython(load_ea600_content, migrations.RunPython.noop)]
