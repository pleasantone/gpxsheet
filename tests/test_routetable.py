"""Tests for the native route table (src/gpxsheet/routetable.py).

Runs on the analyzed synthetic ``table_route.gpx``. It is a sparse ``<rte>``, so
enrichment is skipped (geometry-only, no network) and the table is deterministic
and offline.
"""

from __future__ import annotations

import warnings
from datetime import datetime

import pytest

from gpxsheet import analyze
from gpxsheet.routetable import build_table_markdown, markdown_to_html, parse_departure


@pytest.fixture
def analyzed(table_route_file):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # sparse-route -> geometry-only warning
        return analyze(str(table_route_file))


def test_named_rtepts_become_table_rows(analyzed):
    md = build_table_markdown(analyzed)
    assert "## Route: Table Test Route" in md
    for name in ("Start Cafe", "Nicasio Square", "Shell Gas Station", "Pat's Diner"):
        assert name in md


def test_column_header_and_separator_match_gpxtable(analyzed):
    md = build_table_markdown(analyzed)
    assert "| Name                           |   Dist. | GL |  ETA  | Notes" in md
    assert "| :----------------------------- | ------: | -- | ----: | :----" in md


def test_markers_from_classifier(analyzed):
    rows = {
        line.split("|")[1].strip(): line
        for line in build_table_markdown(analyzed).splitlines()
        if line.startswith("| ") and "Name" not in line and ":---" not in line
    }
    assert rows["Shell Gas Station"].split("|")[3].strip() == "G"
    assert rows["Pat's Diner"].split("|")[3].strip() == "L"
    # First and last rows carry no marker.
    assert rows["Start Cafe"].split("|")[3].strip() == ""
    assert rows["Trailhead"].split("|")[3].strip() == ""


def test_distance_is_cumulative_not_lagged(analyzed):
    # gpxsheet computes true cumulative distance; unlike GPXtable's route path it
    # does NOT lag by one point (Nicasio is ~7 mi in, not 0).
    rows = {
        line.split("|")[1].strip(): line.split("|")[2].strip()
        for line in build_table_markdown(analyzed).splitlines()
        if line.startswith("| ") and "Name" not in line and ":---" not in line
    }
    assert rows["Start Cafe"] == "0"
    assert int(rows["Nicasio Square"]) > 0
    # Fuel stop and the final row use the since-gas/total form.
    assert "/" in rows["Shell Gas Station"]
    assert "/" in rows["Trailhead"]


def test_departure_enables_eta_and_sun(analyzed):
    depart, tz = parse_departure("9:00 AM", "US/Pacific")
    md = build_table_markdown(analyzed, departure=depart, tz=tz)
    assert "* Departure at" in md
    assert "09:00" in md  # first arrival == departure
    assert "Sunrise:" in md and "Sunset:" in md


def test_no_departure_has_no_eta_or_sun(analyzed):
    md = build_table_markdown(analyzed)
    assert "Sunrise:" not in md
    # ETA column is blank (no stray HH:MM times).
    assert "Departure at" not in md


def test_coordinates_columns(analyzed):
    md = build_table_markdown(analyzed, display_coordinates=True)
    assert "Lat,Lon" in md
    assert "38.0000,-122.0000" in md


def test_html_wraps_table(analyzed):
    html = markdown_to_html(build_table_markdown(analyzed))
    assert '<table class="gpxtable">' in html
    assert "<td>" in html


def test_osm_discovered_fuel_appears_in_table(enrich_route_file):
    # The headline win over GPXtable: with OSM on (served from the committed
    # cache), an amenity=fuel station with no rider waypoint becomes a table row.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        route = analyze(str(enrich_route_file), osm=True)
    assert route.fuel_stops, "expected OSM to discover at least one fuel stop"
    md = build_table_markdown(route)
    assert route.fuel_stops[0].name in md


def test_no_osm_skips_enrichment(enrich_route_file):
    # --no-osm stays fully offline: no Overpass call, no discovered fuel.
    route = analyze(str(enrich_route_file), osm=False)
    assert route.fuel_stops == []


def test_osm_speed_profile_drives_variable_eta(analyzed):
    # Inject an OSM speed profile: first half 60 mph, second half 20 mph.
    half = analyzed.length_miles / 2
    analyzed.speed_samples_mph = [(0.0, 60.0), (round(half, 2), 20.0)]
    depart, tz = parse_departure("9:00 AM", "US/Pacific")
    md = build_table_markdown(analyzed, departure=depart, tz=tz)
    assert "* Speed: OSM limits (avg" in md  # variable-speed header


def test_user_speed_overrides_osm_profile(analyzed):
    analyzed.speed_samples_mph = [(0.0, 60.0), (5.0, 10.0)]
    md = build_table_markdown(analyzed, speed=30.0)  # explicit --speed wins
    assert "* Default speed: 30.00 mph" in md
    assert "OSM limits" not in md


def test_parse_departure_optional():
    assert parse_departure(None, None) == (None, None)


def test_parse_departure_returns_datetime_and_tz():
    depart_at, tz = parse_departure("9:00 AM", "US/Pacific")
    assert isinstance(depart_at, datetime)
    assert tz is not None


def test_parse_departure_bad_time():
    with pytest.raises(ValueError, match="invalid departure time"):
        parse_departure("not-a-time", None)


def test_parse_departure_bad_timezone():
    with pytest.raises(ValueError, match="unknown timezone"):
        parse_departure(None, "Mars/Olympus_Mons")
