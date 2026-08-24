"""Geospatial helpers shared by duplicates, dispatch and analytics."""
from __future__ import annotations

import math

CITY_CENTER = (77.5946, 12.9716)  # lon, lat of the demo municipality

# radius (meters) within which a same-class report is considered the same issue
DUPLICATE_RADIUS_M = 60
DUPLICATE_WINDOW_HOURS = 24 * 7


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
