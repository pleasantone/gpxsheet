"""Tests for the GPXtable-backed route-table output (src/gpxsheet/table.py).

Fully offline: GPXtable reads the GPX waypoints directly and never touches OSM.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from gpxsheet import table


def test_build_markdown_has_table_rows(table_route_file):
    gpx = table.parse_gpx(table_route_file)
    md = table.build_table_markdown(gpx)
    assert "## Route: Table Test Route" in md
    assert "| Name" in md and "ETA" in md  # header
    assert "Shell Gas Station" in md  # a data row from the route


def test_markdown_to_html_wraps_table(table_route_file):
    gpx = table.parse_gpx(table_route_file)
    html = table.markdown_to_html(table.build_table_markdown(gpx))
    assert '<table class="gpxtable">' in html
    assert "<td>" in html


def test_render_table_html_and_markdown(tmp_path, table_route_file):
    html_out = table.render_table(table_route_file, tmp_path / "t.html", fmt="html")
    md_out = table.render_table(table_route_file, tmp_path / "t.md", fmt="markdown")
    assert '<table class="gpxtable">' in html_out.read_text()
    assert "## Route: Table Test Route" in md_out.read_text()


def test_route_title_falls_back_to_route_name(table_route_file):
    # No top-level <gpx><name>, so the route name is used.
    assert table.route_title(table.parse_gpx(table_route_file)) == "Table Test Route"


def test_render_table_accepts_bytes(table_route_file, tmp_path):
    data = table_route_file.read_bytes()
    out = table.render_table(data, tmp_path / "t.md", fmt="markdown")
    assert "Table Test Route" in out.read_text()


def test_render_table_rejects_unknown_format(table_route_file, tmp_path):
    with pytest.raises(ValueError, match="fmt must be one of"):
        table.render_table(table_route_file, tmp_path / "t.txt", fmt="csv")


def test_departure_enables_eta(table_route_file):
    depart_at, tz = table.parse_departure("9:00 AM", "US/Pacific")
    assert isinstance(depart_at, datetime)
    md = table.build_table_markdown(table.parse_gpx(table_route_file), depart_at=depart_at, tz=tz)
    assert "Departure" in md


def test_parse_departure_optional():
    assert table.parse_departure(None, None) == (None, None)


def test_parse_departure_bad_time():
    with pytest.raises(ValueError, match="invalid departure time"):
        table.parse_departure("not-a-time", None)


def test_parse_departure_bad_timezone():
    with pytest.raises(ValueError, match="unknown timezone"):
        table.parse_departure(None, "Mars/Olympus_Mons")


def test_parse_gpx_bad_xml_raises_valueerror(tmp_path):
    bad = tmp_path / "bad.gpx"
    bad.write_text("<gpx><trk><trkseg></trk></gpx>")  # mismatched tag
    with pytest.raises(ValueError, match="could not parse GPX"):
        table.parse_gpx(bad)
