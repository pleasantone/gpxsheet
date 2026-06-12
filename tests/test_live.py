"""Tests for the day-card live providers (Phase 2): pure logic + cached I/O.

Deterministic and offline: the autouse ``_live_cache`` fixture (conftest)
points the disk cache at a committed dir and stubs the network seam to cache-only.
Tests that exercise an actual fetch monkeypatch ``base._http_get_json`` to return
a canned payload and redirect the cache to a tmp dir, so nothing hits the network
and the committed fixtures stay clean.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import dateutil.tz
import pytest

from gpxsheet.daycard import _crosswind, build_day_cards, build_day_cards_markdown
from gpxsheet.live import base, fire, weather
from gpxsheet.live.air import fetch_air
from gpxsheet.live.base import SamplePoint
from gpxsheet.live.elevation import fetch_elevation
from gpxsheet.live.fire import fetch_fires
from gpxsheet.live.weather import fetch_weather
from gpxsheet.models import GeoPoint, Route

PT = dateutil.tz.gettz("US/Pacific")


# --- pure logic -----------------------------------------------------------


def test_crosswind_full_when_perpendicular():
    # North-bound road (heading 0), wind from the west (270) -> full crosswind.
    assert _crosswind(0.0, 270.0, 10.0) == 10.0
    assert _crosswind(0.0, 90.0, 10.0) == 10.0


def test_crosswind_zero_when_aligned():
    # Headwind / tailwind contributes no crosswind.
    assert _crosswind(0.0, 0.0, 10.0) == 0.0
    assert _crosswind(0.0, 180.0, 10.0) == 0.0


def test_crosswind_partial_and_none():
    assert _crosswind(0.0, 45.0, 10.0) == pytest.approx(7.1, abs=0.1)
    assert _crosswind(None, 270.0, 10.0) is None
    assert _crosswind(0.0, None, 10.0) is None


def test_nearest_index_picks_closest_hour():
    times = [datetime(2026, 6, 13, h, tzinfo=UTC) for h in range(10, 14)]
    assert weather._nearest_index(times, datetime(2026, 6, 13, 12, 20, tzinfo=UTC)) == 2
    assert weather._nearest_index([], datetime(2026, 6, 13, tzinfo=UTC)) is None


def test_fire_distance_and_bbox():
    import shapely.geometry as sg

    line = sg.LineString([(-121.0, 37.0), (-121.0, 37.5)])
    on_route = sg.Polygon([(-121.01, 37.2), (-120.99, 37.2), (-120.99, 37.3), (-121.01, 37.3)])
    assert fire._distance_miles(line, on_route) == 0.0
    xmin, ymin, xmax, ymax = fire._bbox([(37.0, -121.0), (37.5, -121.0)])
    assert xmin < -121.0 < xmax and ymin < 37.0 and ymax > 37.5


# --- cache + gating -------------------------------------------------------


def test_fetch_json_caches_to_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    calls = {"n": 0}

    def once(url, params):
        calls["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(base, "_http_get_json", once)
    a = base.fetch_json("p", "https://x/y", {"q": 1})
    b = base.fetch_json("p", "https://x/y", {"q": 1})  # served from disk
    assert a == b == {"ok": True}
    assert calls["n"] == 1  # second call did not re-fetch


def test_disable_live_short_circuits(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("GPXSHEET_DISABLE_LIVE", "1")
    monkeypatch.setattr(base, "_http_get_json", lambda url, params: {"ok": True})
    assert base.fetch_json("p", "https://x/y", {"q": 1}) is None


def test_offline_umbrella_short_circuits(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("GPXSHEET_OFFLINE", "1")  # umbrella implies DISABLE_LIVE
    monkeypatch.setattr(base, "_http_get_json", lambda url, params: {"ok": True})
    assert base.fetch_json("p", "https://x/y", {"q": 1}) is None


def test_fetch_swallows_network_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))

    def boom(url, params):
        raise OSError("network down")

    monkeypatch.setattr(base, "_http_get_json", boom)
    assert base.fetch_json("p", "https://x/y", {"q": 1}) is None


def test_key_gated_provider_unavailable_without_key(monkeypatch):
    class Keyed(base.Provider):
        name = "keyed"
        requires_key = "GPXSHEET_TEST_KEY"

    monkeypatch.delenv("GPXSHEET_TEST_KEY", raising=False)
    assert Keyed().available() is False
    monkeypatch.setenv("GPXSHEET_TEST_KEY", "secret")
    assert Keyed().available() is True


# --- provider fetch (canned payloads) -------------------------------------


def _hourly_block(base_date: datetime, **vals: float) -> dict:
    """A 48-hour Open-Meteo location object covering ``base_date`` (UTC)."""
    start = base_date.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
    n = len(times)
    keys = (
        "temperature_2m", "apparent_temperature", "wind_speed_10m", "wind_gusts_10m",
        "wind_direction_10m", "precipitation_probability", "precipitation", "visibility",
        "weather_code",
    )
    hourly: dict = {"time": times}
    for k in keys:
        hourly[k] = [float(vals.get(k, 0.0))] * n
    return {"hourly": hourly}


def test_fetch_weather_parses_and_picks_hour(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    depart = datetime(2026, 6, 13, 9, 0, tzinfo=PT)

    def fake(url, params):
        n = len(params["latitude"].split(","))
        return [_hourly_block(depart, temperature_2m=88, wind_speed_10m=12, visibility_mi=0)
                for _ in range(n)]

    monkeypatch.setattr(base, "_http_get_json", fake)
    pts = [SamplePoint(0.0, 37.0, -121.0, depart, heading=0.0)]
    info = fetch_weather(pts, now=datetime(2026, 6, 12, tzinfo=UTC))
    assert info is not None and info.samples
    assert info.samples[0].temp_f == 88.0
    assert info.samples[0].wind_mph == 12.0


def test_fetch_weather_beyond_horizon(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    far = datetime(2026, 8, 1, 9, 0, tzinfo=PT)  # >16 days past "now"
    pts = [SamplePoint(0.0, 37.0, -121.0, far)]
    info = fetch_weather(pts, now=datetime(2026, 6, 12, tzinfo=UTC))
    assert info is not None and not info.samples and "horizon" in (info.note or "")


def test_fetch_air_flags_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    depart = datetime(2026, 6, 13, 9, 0, tzinfo=PT)
    start = depart.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]

    def fake(url, params):
        n = len(params["latitude"].split(","))
        hourly = {"time": times, "us_aqi": [160] * len(times), "pm2_5": [55.0] * len(times)}
        return [{"hourly": hourly} for _ in range(n)]

    monkeypatch.setattr(base, "_http_get_json", fake)
    info = fetch_air([SamplePoint(0.0, 37.0, -121.0, depart)])
    assert info is not None and info.smoke and info.max_aqi == 160


def test_fetch_elevation(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(base, "_http_get_json", lambda u, p: {"elevation": [100.0, 500.0, 300.0]})
    prof = fetch_elevation([(37.0, -121.0), (37.1, -121.0), (37.2, -121.0)])
    assert prof is not None
    assert prof.max_ft and prof.gain_ft and "Open-Meteo" in prof.source


def test_fetch_fires_intersects_corridor(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"poly_IncidentName": "Canyon Fire",
                               "attr_PercentContained": 30, "attr_IncidentSize": 4200},
                "geometry": {"type": "Polygon", "coordinates": [
                    [[-121.01, 37.24], [-120.99, 37.24], [-120.99, 37.26],
                     [-121.01, 37.26], [-121.01, 37.24]]]},
            }
        ],
    }
    monkeypatch.setattr(base, "_http_get_json", lambda url, params: geojson)
    fires = fetch_fires([(37.0, -121.0), (37.5, -121.0)])
    assert fires and fires[0].name == "Canyon Fire" and fires[0].dist_mi == 0.0
    assert "30% contained" in (fires[0].status or "")


# --- end-to-end through build_day_cards -----------------------------------


def _meridian_route(length_miles: float, n: int = 60) -> Route:
    pts = [GeoPoint(37.0 + i * 0.01, -121.0, None) for i in range(n)]
    dist = [length_miles * 1609.344 * i / (n - 1) for i in range(n)]
    return Route(name="T", points=pts, distances_m=dist)


def test_build_day_cards_populates_live_sections(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    depart = datetime(2026, 6, 13, 9, 0, tzinfo=PT)
    fire_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"poly_IncidentName": "Ridge Fire", "attr_PercentContained": 10},
            "geometry": {"type": "Polygon", "coordinates": [
                [[-121.01, 37.24], [-120.99, 37.24], [-120.99, 37.26],
                 [-121.01, 37.26], [-121.01, 37.24]]]},
        }],
    }

    def dispatch(url, params):
        if "air-quality" in url:
            start = depart.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
            n = len(params["latitude"].split(","))
            return [{"hourly": {"time": times, "us_aqi": [40] * len(times),
                                "pm2_5": [8.0] * len(times)}} for _ in range(n)]
        if url.endswith("/elevation"):
            return {"elevation": [200.0] * len(params["latitude"].split(","))}
        if "forecast" in url:
            n = len(params["latitude"].split(","))
            # Wind from the west on a north-bound route -> strong crosswind.
            return [_hourly_block(depart, temperature_2m=72, wind_speed_10m=28,
                                  wind_gusts_10m=40, wind_direction_10m=270,
                                  precipitation_probability=10, visibility_mi=0)
                    for _ in range(n)]
        if "Perimeters" in url:
            return fire_geojson
        return None

    monkeypatch.setattr(base, "_http_get_json", dispatch)
    route = _meridian_route(40.0)
    cards = build_day_cards(route, departure=depart, tz=PT, speed=30.0, osm=False, live=True)
    card = cards[0]
    assert card.weather is not None and card.weather.samples
    assert any(s.crosswind_mph and s.crosswind_mph > 20 for s in card.weather.samples)
    assert card.air is not None
    assert card.fire and card.fire[0].name == "Ridge Fire"
    codes = {w.code for w in card.warnings}
    assert {"wind", "fire"} <= codes
    md = build_day_cards_markdown(cards)
    assert "Weather:" in md and "Fires:" in md
    data = card.to_dict()
    assert "weather" in data and data["weather"]["samples"]


def test_live_disabled_skips_sections(monkeypatch, tmp_path):
    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("GPXSHEET_DISABLE_LIVE", "1")
    monkeypatch.setattr(base, "_http_get_json", lambda url, params: {"hourly": {}})
    depart = datetime(2026, 6, 13, 9, 0, tzinfo=PT)
    cards = build_day_cards(
        _meridian_route(40.0), departure=depart, speed=30.0, osm=False, live=True
    )
    assert cards[0].weather is None and cards[0].air is None and not cards[0].fire


def test_live_queries_are_perf_instrumented(monkeypatch, tmp_path):
    from gpxsheet import perf

    monkeypatch.setenv("GPXSHEET_LIVE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(base, "_http_get_json", lambda url, params: None)  # fast skip
    depart = datetime(2026, 6, 13, 9, 0, tzinfo=PT)
    with perf.track("job:daycard") as rec:
        build_day_cards(_meridian_route(40.0), departure=depart, speed=30.0, osm=False, live=True)
    names = {n for n, _ in rec.spans}
    assert {"daycard.weather", "daycard.air", "daycard.elevation", "daycard.fire"} <= names
