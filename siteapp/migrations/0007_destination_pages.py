from collections import Counter

import django.db.models.deletion
import modelcluster.fields
from django.db import migrations, models
from django.utils.text import slugify


def prepare_destinations(apps, schema_editor):
    database = schema_editor.connection.alias
    destinations = list(apps.get_model("siteapp", "Destination").objects.using(database).order_by("pk"))
    stops = apps.get_model("siteapp", "TourStop").objects.using(database)
    title_counts = Counter(destination.title.casefold() for destination in destinations)
    used_slugs = set()

    for destination in destinations:
        base = slugify(destination.title) or "destination"
        slug = base
        number = 2
        while slug in used_slugs:
            slug = f"{base}-{number}"
            number += 1
        used_slugs.add(slug)
        destination.slug = slug
        destination.save(update_fields=["slug"], using=database)

        if title_counts[destination.title.casefold()] == 1:
            stops.filter(
                tour__slug__in=("ea600", "ea600-3-day", "ea600-14-day"),
                title__iexact=destination.title,
            ).update(destination_id=destination.pk)


class Migration(migrations.Migration):
    dependencies = [("siteapp", "0006_ea600_itineraries")]

    operations = [
        migrations.AddField(
            model_name="destination",
            name="slug",
            field=models.SlugField(max_length=160, null=True),
        ),
        migrations.AddField(
            model_name="tourstop",
            name="destination",
            field=models.ForeignKey(
                blank=True,
                help_text="Link to the public destination page and show this stop’s eligible business listings there.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="route_stops",
                to="siteapp.destination",
            ),
        ),
        migrations.RunPython(prepare_destinations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="destination",
            name="slug",
            field=models.SlugField(help_text="Keep this part of the public URL stable.", max_length=160, unique=True),
        ),
        migrations.CreateModel(
            name="DestinationPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.IntegerField(blank=True, editable=False, null=True)),
                ("destination", modelcluster.fields.ParentalKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name="gallery", to="siteapp.destination",
                )),
                ("photo", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name="+", to="siteapp.photo",
                )),
            ],
            options={"ordering": ["sort_order"]},
        ),
    ]
