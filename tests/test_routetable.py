"""Tests for the native route table (src/gpxsheet/routetable.py).

Runs on the analyzed synthetic ``table_route.gpx``. It is a sparse ``<rte>``, so
enrichment is skipped (geometry-only, no network) and the table is deterministic
and offline.
"""

from __future__ import annotations

import warnings

import pytest

from gpxsheet import analyze
from gpxsheet.routetable import build_table_markdown, markdown_to_html
from gpxsheet.table import parse_departure


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
