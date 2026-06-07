"""Tests for OSM enrichment.

The pure helpers are tested without network access (they only need pandas, which
ships with the ``osm`` extra, so the whole module is skipped when osmnx/pandas
is absent — e.g. in core-only CI). The end-to-end ``enrich_route`` path hits the
live Overpass API and only runs when GPXSHEET_LIVE_OSM=1 is set.
"""

from __future__ import annotations

import os

import pytest

from gpxsheet.enrich import osm_available

pytestmark = pytest.mark.skipif(not osm_available(), reason="requires the osm extra")


def _edges_frame():
    import pandas as pd

    idx = pd.MultiIndex.from_tuples([(1, 2, 0), (3, 4, 0), (5, 6, 0)])
    names = ["Skaggs Springs Rd", ["CA-1", "Coast Hwy"], float("nan")]
    return pd.DataFrame({"name": names}, index=idx)


def test_edge_name_handles_str_list_and_nan():
    from gpxsheet.enrich import _edge_name

    df = _edges_frame()
    assert _edge_name(df, (1, 2, 0)) == "Skaggs Springs Rd"
    assert _edge_name(df, (3, 4, 0)) == "CA-1"  # list -> first element
    assert _edge_name(df, (5, 6, 0)) is None  # NaN
    assert _edge_name(df, (9, 9, 9)) is None  # missing key


def test_edge_name_missing_column():
    import pandas as pd

    from gpxsheet.enrich import _edge_name

    df = pd.DataFrame({"other": [1]}, index=pd.MultiIndex.from_tuples([(1, 2, 0)]))
    assert _edge_name(df, (1, 2, 0)) is None


def test_coord_at_meters_picks_nearest_point():
    from gpxsheet.enrich import _coord_at_meters
    from gpxsheet.models import GeoPoint, Route

    pts = [GeoPoint(0.0, float(i)) for i in range(5)]
    route = Route(name="x", points=pts, distances_m=[0.0, 100.0, 200.0, 300.0, 400.0])
    assert _coord_at_meters(route, 0.0) == (0.0, 0.0)
    assert _coord_at_meters(route, 205.0) == (0.0, 3.0)  # rounds up to next vertex
    assert _coord_at_meters(route, 10_000.0) == (0.0, 4.0)  # clamped to end


@pytest.mark.skipif(
    os.environ.get("GPXSHEET_LIVE_OSM") != "1",
    reason="live Overpass query; set GPXSHEET_LIVE_OSM=1 to run",
)
def test_enrich_route_live_against_osm():
    from gpxsheet import load_route
    from gpxsheet.analysis import analyze_route
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import Route

    full = load_route("/Users/pst/gpxtable/samples/gaia.gpx")
    clip = [p for p, d in zip(full.points, full.distances_m, strict=False) if d < 15 * 1609.344]
    route = Route(
        name="live", points=clip, distances_m=cumulative_distances([(p.lat, p.lon) for p in clip])
    )
    analyze_route(route, profile="sport-touring", use_osm=True)
    # Segments should pick up at least one real OSM road name (not just "Leg N").
    assert any(not s.name.startswith("Leg ") for s in route.segments)
