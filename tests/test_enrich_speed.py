"""Tests for OSM speed-limit sampling (src/gpxsheet/enrich.py)."""

from __future__ import annotations

from gpxsheet.enrich import (
    _edge_speed_mph,
    _parse_maxspeed_mph,
    _speed_breakpoints,
)


def test_parse_maxspeed_mph_units():
    assert _parse_maxspeed_mph("55 mph") == 55.0
    assert round(_parse_maxspeed_mph("80"), 0) == 50.0  # 80 km/h ~= 49.7 mph
    assert _parse_maxspeed_mph(None) is None
    assert _parse_maxspeed_mph("none") is None
    assert _parse_maxspeed_mph("signals") is None


def test_edge_speed_prefers_posted_then_class():
    assert _edge_speed_mph("45 mph", "residential") == 45.0  # posted wins
    assert _edge_speed_mph(None, "motorway") == 70.0  # class default
    assert _edge_speed_mph(None, "unknownclass") == 35.0  # fallback default
    assert _edge_speed_mph(None, None) is None  # no data


def test_speed_breakpoints_coalesce_and_fill():
    sample_m = [0.0, 1609.344, 3218.688, 4828.032]  # 0,1,2,3 miles
    speeds = [None, 60.0, 60.0, 30.0]
    bps = _speed_breakpoints(sample_m, speeds)
    # Leading None back-filled to 60; the run of 60s collapses; change at mile 3.
    assert bps == [(0.0, 60.0), (3.0, 30.0)]


def test_speed_breakpoints_all_none():
    assert _speed_breakpoints([0.0, 100.0], [None, None]) is None
