"""Geometry helpers: distances and bearings on the WGS-84 sphere.

Distances are computed with the haversine formula and kept internally in
meters. Miles are the user-facing unit (see :data:`METERS_PER_MILE`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (IUGG)
METERS_PER_MILE = 1609.344


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE


def miles_to_meters(miles: float) -> float:
    return miles * METERS_PER_MILE


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2, in degrees [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def bearing_delta(b1: float, b2: float) -> float:
    """Signed smallest turn from bearing b1 to b2, in degrees (-180, 180].

    Positive = turn to the right (clockwise), negative = turn to the left.
    """
    d = (b2 - b1 + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def cumulative_distances(points: Sequence[tuple[float, float]]) -> list[float]:
    """Cumulative along-track distance (meters) for each point; first is 0."""
    out = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:], strict=False):
        out.append(out[-1] + haversine(lat1, lon1, lat2, lon2))
    return out
