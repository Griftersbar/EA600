from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404


def home(request):
    index_file = Path(settings.BASE_DIR) / "index.html"
    if not index_file.exists():
        raise Http404("The EA600 landing page could not be found.")
    return FileResponse(index_file.open("rb"), content_type="text/html")
