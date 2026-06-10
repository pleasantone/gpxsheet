"""Geometry cleanup via Ramer-Douglas-Peucker simplification.

Used as the "Geometry Cleanup" pipeline stage in docs/product.md: it strips GPS
noise and redundant points before bearing/turn analysis, which makes
decision-point detection far more robust on recorded tracks. docs/product.md targets
95%+ point reduction for recorded tracks.

This is a planar RDP using the equirectangular approximation, which is more than
accurate enough at the small tolerances (~10 m) used for cleanup.
"""

from __future__ import annotations

import math

from .geo import EARTH_RADIUS_M
from .models import GeoPoint


def _perp_distance_m(p: GeoPoint, a: GeoPoint, b: GeoPoint) -> float:
    """Perpendicular distance (m) from point p to segment a-b, equirectangular."""
    lat0 = math.radians((a.lat + b.lat) / 2.0)

    def xy(pt: GeoPoint) -> tuple[float, float]:
        x = math.radians(pt.lon) * math.cos(lat0) * EARTH_RADIUS_M
        y = math.radians(pt.lat) * EARTH_RADIUS_M
        return x, y

    px, py = xy(p)
    ax, ay = xy(a)
    bx, by = xy(b)

    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def rdp(points: list[GeoPoint], tolerance_m: float) -> list[GeoPoint]:
    """Ramer-Douglas-Peucker simplification keeping points > tolerance_m.

    Returns a new list; endpoints are always preserved. An iterative stack is
    used to avoid recursion limits on long recorded tracks.
    """
    n = len(points)
    if n < 3 or tolerance_m <= 0:
        return list(points)

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        dmax, idx = 0.0, start
        for i in range(start + 1, end):
            d = _perp_distance_m(points[i], points[start], points[end])
            if d > dmax:
                dmax, idx = d, i
        if dmax > tolerance_m:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))

    return [p for p, k in zip(points, keep, strict=True) if k]
