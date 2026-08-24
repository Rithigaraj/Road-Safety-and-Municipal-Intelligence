"""Extract GPS coordinates from JPEG EXIF metadata.

Lets citizens report with zero typing: the phone camera embeds the location.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ExifTags


def gps_from_bytes(data: bytes) -> tuple[float, float] | None:
    try:
        img = Image.open(BytesIO(data))
        exif = img._getexif()  # noqa: SLF001 - public-ish Pillow API
    except Exception:
        return None
    if not exif:
        return None

    tags = {ExifTags.TAGS.get(k): v for k, v in exif.items()}
    gps = tags.get("GPSInfo")
    if not gps:
        return None

    def _deg(val) -> float | None:
        try:
            d, m, s = val
            return float(d) + float(m) / 60.0 + float(s) / 3600.0
        except Exception:
            return None

    try:
        lat = _deg(gps[2])
        lon = _deg(gps[4])
        if lat is None or lon is None:
            return None
        if gps.get(1) == "S":
            lat = -lat
        if gps.get(3) == "W":
            lon = -lon
        if abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0):
            return None
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None
