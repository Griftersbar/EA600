import json
import os
from datetime import date
from pathlib import Path

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.views.decorators.http import require_safe


NOTES_PATH = Path(__file__).with_name("release_notes.json")


def load_release_notes():
    releases = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    for release in releases:
        release["date"] = date.fromisoformat(release["date"])
    return releases


@require_safe
def release_notes(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    releases = load_release_notes()
    return TemplateResponse(request, "admin/release_notes.html", {
        **admin.site.each_context(request),
        "title": "Release notes",
        "current_version": releases[0]["version"],
        "build_revision": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:8],
        "releases": releases,
    })
