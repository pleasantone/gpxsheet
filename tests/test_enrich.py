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


def test_durable_runs_drops_transient_flaps():
    # Sampled every 100 m: a one-sample flap onto "Cross St" must be discarded;
    # the surrounding "Main St" run rejoins into a single run.
    from gpxsheet.enrich import _durable_runs

    sample_m = [i * 100.0 for i in range(12)]  # 0..1100 m, 12 samples
    names = ["Main St"] * 5 + ["Cross St"] + ["Main St"] * 5 + ["Highway 1"]
    runs = _durable_runs(sample_m, names, min_run_m=300.0)
    road_names = [n for _, n in runs]
    assert "Cross St" not in road_names  # transient flap dropped
    assert road_names.count("Main St") == 1  # rejoined into one run
    assert road_names[-1] == "Highway 1"  # last run kept even though short (edge)


def test_clean_str_handles_nan_and_blanks():
    from gpxsheet.enrich import _clean_str

    assert _clean_str("Shell") == "Shell"
    assert _clean_str(float("nan")) is None  # NaN is truthy -> must be filtered explicitly
    assert _clean_str(None) is None
    assert _clean_str("  ") is None


def test_road_change_instruction_and_significance():
    from gpxsheet.enrich import _is_highway, _road_change_significance

    assert _is_highway("James Lick Freeway")
    assert _is_highway("CA-1")
    assert not _is_highway("Skaggs Springs Rd")
    # Highway change scores higher than a plain residential road change.
    assert _road_change_significance("CA-1", 10.0) > _road_change_significance("Elm St", 10.0)


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
    # Segments should be real OSM road names, not generic "Leg N".
    assert route.segments
    assert all(not s.name.startswith("Leg ") for s in route.segments)
    # Decisions come from road-name changes -> every instruction names a road.
    assert route.decision_points
    assert all("onto" in d.instruction for d in route.decision_points)
    # The point of the tuning: decisions track real road changes, not the road's
    # curvature, so the count stays bounded (no per-curve flood).
    assert len(route.decision_points) / route.length_miles < 1.0
