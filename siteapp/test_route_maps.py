import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import Tour
from .test_support import sign_in_verified


OPEN_GPX = b"""<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="EA600 test">
  <rte>
    <rtept lat="51.64" lon="-2.67"/>
    <rtept lat="51.78" lon="-2.72"/>
    <rtept lat="51.91" lon="-2.59"/>
  </rte>
</gpx>"""
LOOP_GPX = b"""<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="EA600 test">
  <trk><trkseg>
    <trkpt lat="52.63" lon="1.3"/>
    <trkpt lat="52.69" lon="1.42"/>
  </trkseg><trkseg>
    <trkpt lat="52.7" lon="1.43"/>
    <trkpt lat="52.63" lon="1.3"/>
  </trkseg></trk>
</gpx>"""


class RouteMapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(username="map-editor")

    def setUp(self):
        sign_in_verified(self.client, self.editor)

    def import_track(self, gpx):
        return self.client.post(reverse("builder_import_gpx"), {
            "gpx": SimpleUploadedFile("route.gpx", gpx, content_type="application/gpx+xml"),
        })

    def test_imported_paths_and_stops_survive_preview_draft_and_publish(self):
        for title, slug, gpx, expected in (
            ("Wye Valley test", "wye-valley-test", OPEN_GPX, [[[51.64, -2.67], [51.78, -2.72], [51.91, -2.59]]]),
            ("Norfolk loop test", "norfolk-loop-test", LOOP_GPX, [
                [[52.63, 1.3], [52.69, 1.42]], [[52.7, 1.43], [52.63, 1.3]],
            ]),
        ):
            with self.subTest(title=title):
                imported = self.import_track(gpx)
                self.assertEqual(imported.status_code, 200)
                track = imported.json()["track"]
                self.assertEqual(track, expected)
                latitude, longitude = expected[0][0]
                data = {
                    "title": title, "slug": slug, "summary": "Test route map", "position": 1,
                    "route_track": json.dumps(track),
                    "stops-TOTAL_FORMS": 1, "stops-INITIAL_FORMS": 0,
                    "stops-0-title": "First stop", "stops-0-ORDER": 1,
                    "stops-0-latitude": latitude, "stops-0-longitude": longitude,
                    "days-TOTAL_FORMS": 0, "days-INITIAL_FORMS": 0,
                }
                new = reverse("builder_new")
                preview = self.client.post(new, {**data, "action": "preview"})
                self.assertContains(preview, "data-geographic-route")
                self.assertEqual(preview.context["geographic_map"]["track"], expected)
                self.assertEqual(
                    preview.context["geographic_map"]["stops"],
                    [{"number": 1, "title": "First stop", "position": [latitude, longitude]}],
                )
                self.assertFalse(Tour.objects.filter(slug=slug).exists())
                draft = self.client.post(new, {**data, "action": "draft"})
                self.assertEqual(draft.status_code, 302)
                tour = Tour.objects.get(slug=slug)
                stop = tour.stops.get()
                self.assertEqual(stop.latitude, Decimal(str(latitude)))
                self.assertEqual(stop.longitude, Decimal(str(longitude)))
                self.assertEqual(Client().get(tour.get_absolute_url()).status_code, 404)
                edit = reverse("builder_edit", args=[tour.pk])
                edit_data = {
                    **data, "version": self.client.get(edit).context["version"],
                    "stops-INITIAL_FORMS": 1, "stops-0-id": stop.pk, "action": "publish",
                }
                self.assertRedirects(self.client.post(edit, edit_data), edit)
                detail = Client().get(tour.get_absolute_url())
                self.assertContains(detail, "data-geographic-route")
                self.assertEqual(detail.context["geographic_map"]["track"], expected)

    def test_invalid_import_and_tracking_data_are_rejected(self):
        self.assertEqual(self.import_track(b"<gpx><rte>").status_code, 400)
        self.assertEqual(
            self.import_track(b'<?xml version="1.0" encoding="unsupported"?><gpx/>').status_code, 400,
        )
        self.assertEqual(
            self.import_track(OPEN_GPX.replace(b'lat="51.64"', b'lat="91"')).status_code, 400,
        )
        self.assertContains(
            self.client.post(reverse("builder_new"), {
                "title": "Invalid track", "slug": "invalid-track", "summary": "Invalid track", "position": 0,
                "route_track": json.dumps([[[50, -2], [51, -181]]]), "action": "publish",
                "stops-TOTAL_FORMS": 0, "stops-INITIAL_FORMS": 0,
                "days-TOTAL_FORMS": 0, "days-INITIAL_FORMS": 0,
            }),
            "invalid latitude or longitude",
        )
        self.assertFalse(Tour.objects.filter(slug="invalid-track").exists())

    def test_gpx_import_requires_a_verified_editor(self):
        url = reverse("builder_import_gpx")
        self.assertEqual(Client().post(url).status_code, 302)
        staff = get_user_model().objects.create_user(username="no-tour-rights", is_staff=True)
        sign_in_verified(self.client, staff)
        self.assertEqual(self.import_track(OPEN_GPX).status_code, 403)

    def test_gpx_only_tour_displays_map_and_existing_tour_keeps_illustration(self):
        tour = Tour.objects.create(
            title="Track only", slug="track-only", summary="GPX track before adding stops",
            route_track=[[[51.64, -2.67], [51.91, -2.59]]], is_published=True,
        )
        self.assertContains(self.client.get(tour.get_absolute_url()), "data-geographic-route")
        legacy = self.client.get(reverse("tour_detail", args=["ea600"]))
        self.assertContains(legacy, "route-map-frame__img")
        self.assertIsNone(legacy.context["geographic_map"])
