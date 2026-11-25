from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring
from django.core.exceptions import ValidationError


MAX_GPX_BYTES = 2 * 1024 * 1024
MAX_TRACK_POINTS = 25_000
GPX_ROOTS = {"gpx", "{http://www.topografix.com/GPX/1/0}gpx", "{http://www.topografix.com/GPX/1/1}gpx"}


def validate_route_track(track):
    """Validate a list of segments, each made of latitude/longitude pairs."""
    if not isinstance(track, list):
        raise ValidationError("Import a GPX route to set the map track.")
    point_count = 0
    for segment in track:
        if not isinstance(segment, list) or len(segment) < 2:
            raise ValidationError("Each route segment must contain at least two points.")
        point_count += len(segment)
        if point_count > MAX_TRACK_POINTS:
            raise ValidationError("A route can contain up to 25,000 track points.")
        for point in segment:
            if (
                not isinstance(point, list) or len(point) != 2
                or any(type(value) not in (int, float) for value in point)
                or not -90 <= point[0] <= 90 or not -180 <= point[1] <= 180
            ):
                raise ValidationError("The track contains an invalid latitude or longitude.")


def read_gpx(file):
    if file.size > MAX_GPX_BYTES:
        raise ValidationError("Choose a GPX file no larger than 2 MB.")
    try:
        root = fromstring(file.read(MAX_GPX_BYTES + 1), forbid_dtd=True)
    except (ParseError, DefusedXmlException, LookupError, ValueError) as error:
        raise ValidationError("Choose a valid GPX file.") from error
    if root.tag not in GPX_ROOTS:
        raise ValidationError("Choose a valid GPX file.")

    segments = [element.findall("{*}trkpt") for element in root.findall("{*}trk/{*}trkseg")]
    segments = [segment for segment in segments if len(segment) >= 2]
    if not segments:
        segments = [element.findall("{*}rtept") for element in root.findall("{*}rte")]
        segments = [segment for segment in segments if len(segment) >= 2]
    if not segments:
        raise ValidationError("The GPX file must contain a track or route with at least two points.")
    if sum(map(len, segments)) > MAX_TRACK_POINTS:
        raise ValidationError("A route can contain up to 25,000 track points.")

    try:
        track = [
            [[float(point.attrib["lat"]), float(point.attrib["lon"])] for point in segment]
            for segment in segments
        ]
    except (KeyError, ValueError) as error:
        raise ValidationError("The track contains an invalid latitude or longitude.") from error
    validate_route_track(track)
    return [[[round(lat, 6), round(lng, 6)] for lat, lng in segment] for segment in track]
