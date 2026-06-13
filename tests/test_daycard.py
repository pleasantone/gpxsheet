"""Tests for day cards (pure; no network)."""

from __future__ import annotations

import json
from datetime import datetime

import dateutil.tz

from gpxsheet.daycard import (
    _after_dark,
    _classify_pois,
    _service_gaps,
    build_day_cards,
    build_day_cards_json,
    build_day_cards_markdown,
)
from gpxsheet.models import FuelStop, GeoPoint, Route, RouteSpan, SpanKind
from gpxsheet.timing import SpeedProfile

PT = dateutil.tz.gettz("US/Pacific")


def _route(length_miles: float, *, n: int = 60, ele=None, day_breaks=(), **kw) -> Route:
    """A synthetic route up a meridian with a linear distance ramp."""
    pts = [GeoPoint(37.0 + i * 0.01, -121.0, None if ele is None else ele[i]) for i in range(n)]
    dist = [length_miles * 1609.344 * i / (n - 1) for i in range(n)]
    return Route(name="T", points=pts, distances_m=dist, day_breaks=list(day_breaks), **kw)


def test_single_day_basic():
    cards = build_day_cards(_route(100.0), osm=False)
    assert len(cards) == 1
    assert abs(cards[0].miles - 100.0) < 1.0
    assert cards[0].moving_time is not None  # computed even without a departure


def test_multiday_splits_on_day_breaks():
    cards = build_day_cards(_route(100.0, n=61, day_breaks=[30]), osm=False)
    assert len(cards) == 2
    # The two days partition the route; miles add up to the whole.
    assert abs(sum(c.miles for c in cards) - 100.0) < 1.0


def test_elevation_gain_and_big_climb_warning():
    # Climb 0->2400 m (~7874 ft) over the first half, then flat.
    ele = [min(i, 30) * 80.0 for i in range(60)]
    cards = build_day_cards(_route(50.0, ele=ele), osm=False)
    assert cards[0].elevation_gain_ft is not None
    assert cards[0].elevation_gain_ft > 6000
    assert any(w.code == "climb" for w in cards[0].warnings)


def test_no_elevation_when_track_has_none():
    cards = build_day_cards(_route(50.0), osm=False)  # ele=None
    assert cards[0].elevation_gain_ft is None


def test_gravel_warning_from_spans():
    route = _route(50.0, spans=[RouteSpan(10.0, 13.0, SpanKind.UNPAVED, "Forest Rd")])
    cards = build_day_cards(route, osm=False)
    assert any(w.code == "unpaved" for w in cards[0].warnings)


def test_service_gaps_and_warning():
    # Fuel only at mile 5; a 50 mi route -> a long gap to the end.
    gaps = _service_gaps(_route(50.0, fuel_stops=[FuelStop(5, "Gas", 37, -121)]), 0.0, 50.0, 30.0)
    assert gaps and gaps[-1].miles > 30
    route = _route(50.0, fuel_stops=[FuelStop(5, "Gas", 37, -121)])
    cards = build_day_cards(route, fuel_range=40.0, osm=False)  # gap 45 mi > 40 range
    assert any(w.code == "services" for w in cards[0].warnings)


def test_after_dark_pure():
    depart = datetime(2026, 7, 4, 15, 0, tzinfo=PT)
    sunset = datetime(2026, 7, 4, 20, 30, tzinfo=PT)
    prof = SpeedProfile.flat(30.0)
    # 300 mi at 30 mph = 10 h -> finishes ~01:00, well after sunset.
    dark, mile = _after_dark(prof, depart, sunset, 300.0)
    assert dark and mile is not None and 150 < mile < 180  # ~5.5 h in -> ~165 mi
    # A short day in daylight: no after-dark.
    assert _after_dark(prof, depart, sunset, 60.0) == (False, None)
    # No sunset known -> not flagged.
    assert _after_dark(prof, depart, None, 300.0) == (False, None)


def test_departure_enables_sun_and_after_dark_warning():
    depart = datetime(2026, 7, 4, 15, 0, tzinfo=PT)
    cards = build_day_cards(_route(300.0), departure=depart, tz=PT, speed=30.0, osm=False)
    assert cards[0].sun is not None and cards[0].sun.sunset is not None
    assert cards[0].sun.after_dark
    assert any(w.code == "dark" for w in cards[0].warnings)


def test_static_only_without_departure():
    cards = build_day_cards(_route(300.0), speed=30.0, osm=False)
    assert cards[0].sun is None
    assert cards[0].date is None
    assert not any(w.code == "dark" for w in cards[0].warnings)


def test_classify_pois_pure():
    route = _route(50.0)
    far = route.points[40]  # ~mile 33
    near = route.points[10]  # ~mile 8
    rows = [
        {"name": "Sonora Pass", "lat": far.lat, "lon": far.lon, "ele": "2933",
         "mountain_pass": "yes"},
        {"name": "Vista Point", "lat": near.lat, "lon": near.lon, "tourism": "viewpoint"},
        {"name": "", "lat": near.lat, "lon": near.lon, "highway": "construction"},
        {"name": "Elk Crossing", "lat": near.lat, "lon": near.lon, "hazard": "animal_crossing"},
    ]
    out = _classify_pois(rows, route)
    assert len(out["passes"]) == 1 and out["passes"][0].elevation_ft == 9623
    assert out["scenic"][0].name == "Vista Point"
    assert out["construction"] and out["wildlife"]


def test_renderers_markdown_and_json():
    cards = build_day_cards(_route(100.0, n=61, day_breaks=[30]), osm=False)
    md = build_day_cards_markdown(cards)
    assert "## Day 1" in md and "## Day 2" in md
    data = json.loads(build_day_cards_json(cards))
    assert isinstance(data, list) and len(data) == 2
    assert {"index", "miles", "warnings", "moving_minutes"} <= set(data[0])


def test_markdown_includes_cautions_and_attribution():
    # The markdown should carry every section the structured card does, not just
    # the stats/weather summary it used to.
    depart = datetime(2026, 7, 4, 15, 0, tzinfo=PT)
    route = _route(
        300.0,
        spans=[RouteSpan(10.0, 13.0, SpanKind.UNPAVED, "Forest Rd")],
        fuel_stops=[FuelStop(5, "Gas", 37, -121)],
    )
    cards = build_day_cards(
        route, departure=depart, tz=PT, speed=30.0, fuel_range=40.0, osm=False
    )
    md = build_day_cards_markdown(cards, tz=PT)
    assert "Gravel/unpaved:" in md
    assert "No services:" in md
    assert "riding after dark" in md  # after-dark detail on the sun line
    assert "Golden hour:" in md
    assert "Sources:" in md and "OpenStreetMap" in md  # attribution always present


def test_end_to_end_on_cached_fixture(enrich_route_file):
    # Uses the committed OSM cache for enrichment; the day-card POI query degrades
    # offline (cache miss) but the card still builds from the analyzed route.
    from gpxsheet.daycard import render_day_cards

    out = render_day_cards(str(enrich_route_file), "/tmp/gpxsheet_daycards.md", osm=True)
    text = out.read_text()
    assert "## Day 1" in text or "## Day" in text
