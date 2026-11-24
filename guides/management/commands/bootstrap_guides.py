from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.models import Page, Site

from guides.models import DestinationGuidePage, GuideIndexPage
from siteapp.models import Destination, Tour


class Command(BaseCommand):
    help = "Set up the Guides section on the first Wagtail deployment."

    @transaction.atomic
    def handle(self, *args, **options):
        if GuideIndexPage.objects.exists():
            return

        index = Page.get_first_root_node().add_child(instance=GuideIndexPage(
            title="Guides",
            slug="guides",
            introduction="Explore the places along the EA600.",
        ))
        index.save_revision().publish()
        site = Site.objects.filter(is_default_site=True).first() or Site(is_default_site=True)
        site.root_page = index
        base_url = urlsplit(settings.WAGTAILADMIN_BASE_URL)
        site.hostname = base_url.hostname
        site.port = base_url.port or (443 if base_url.scheme == "https" else 80)
        site.site_name = "EA600 Guides"
        site.save()

        destination = Destination.objects.filter(title="Norwich").select_related("photo").first()
        if destination:
            tour = Tour.objects.filter(slug="ea600", is_published=True).first()
            guide = index.add_child(instance=DestinationGuidePage(
                title=destination.title,
                slug="norwich",
                introduction=destination.description,
                cover=destination.photo,
                body=[("featured_tour", tour)] if tour else [],
            ))
            guide.save_revision().publish()

        self.stdout.write(self.style.SUCCESS("EA600 Guides created."))
