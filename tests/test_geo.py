"""Tests for geometry helpers."""

import math

from gpxsheet.geo import bearing, bearing_delta, cumulative_distances, haversine, meters_to_miles


def test_haversine_known_distance():
    # 1 degree of latitude is ~111 km.
    d = haversine(0.0, 0.0, 1.0, 0.0)
    assert math.isclose(d, 111_195, rel_tol=1e-3)


def test_haversine_zero():
    assert haversine(38.0, -123.0, 38.0, -123.0) == 0.0


def test_bearing_cardinal_directions():
    assert math.isclose(bearing(0, 0, 1, 0), 0.0, abs_tol=1e-6)  # north
    assert math.isclose(bearing(0, 0, 0, 1), 90.0, abs_tol=1e-6)  # east


def test_bearing_delta_sign():
    # East (90) then North (0) is a left turn -> negative.
    assert bearing_delta(90, 0) == -90
    # North (0) then East (90) is a right turn -> positive.
    assert bearing_delta(0, 90) == 90


def test_cumulative_distances_monotonic():
    pts = [(38.0, -123.0), (38.0, -122.999), (38.001, -122.999)]
    cum = cumulative_distances(pts)
    assert cum[0] == 0.0
    assert cum[1] < cum[2]
    assert len(cum) == len(pts)


def test_meters_to_miles():
    assert math.isclose(meters_to_miles(1609.344), 1.0)
