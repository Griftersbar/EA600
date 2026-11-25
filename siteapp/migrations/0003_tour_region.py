from django.db import migrations, models


def label_ea600_region(apps, schema_editor):
    Tour = apps.get_model("siteapp", "Tour")
    Tour.objects.using(schema_editor.connection.alias).filter(slug="ea600", region="").update(region="East Anglia")


class Migration(migrations.Migration):
    dependencies = [("siteapp", "0002_ea600_content")]

    operations = [
        migrations.AddField(
            model_name="tour",
            name="region",
            field=models.CharField(max_length=120, blank=True, help_text="Shown on route cards."),
        ),
        migrations.RunPython(label_ea600_region, migrations.RunPython.noop),
    ]
