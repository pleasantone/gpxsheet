"""Tests for OSM enrichment.

The pure helpers run without network access. The end-to-end ``enrich_route`` path
runs against committed Overpass responses (``tests/fixtures/osm_cache``) wired up
by ``conftest``, so it is deterministic and offline; re-record with
``GPXSHEET_RECORD_OSM=1``.
"""

from __future__ import annotations


def _edges_frame():
    import pandas as pd

    idx = pd.MultiIndex.from_tuples([(1, 2, 0), (3, 4, 0), (5, 6, 0)])
    names = ["Skaggs Springs Rd", ["CA-1", "Coast Hwy"], float("nan")]
    return pd.DataFrame({"name": names}, index=idx)


def test_configure_osm_cache_honors_env(monkeypatch):
    from types import SimpleNamespace

    from gpxsheet.enrich import _configure_osm_cache

    ox = SimpleNamespace(settings=SimpleNamespace(cache_folder="cache"))
    # Unset -> no-op (leaves osmnx default / conftest's wiring alone).
    monkeypatch.delenv("GPXSHEET_OSM_CACHE_DIR", raising=False)
    _configure_osm_cache(ox)
    assert ox.settings.cache_folder == "cache"
    # Set -> points osmnx at the writable dir.
    monkeypatch.setenv("GPXSHEET_OSM_CACHE_DIR", "/tmp/gpxsheet-osm-cache")
    _configure_osm_cache(ox)
    assert ox.settings.cache_folder == "/tmp/gpxsheet-osm-cache"


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
    road_names = [r.name for r in runs]
    assert "Cross St" not in road_names  # transient flap dropped
    assert road_names.count("Main St") == 1  # rejoined into one run
    assert road_names[-1] == "Highway 1"  # last run kept even though short (edge)


def test_unpaved_spans_run_length_encode():
    from gpxsheet.enrich import _unpaved_spans
    from gpxsheet.models import SpanKind

    # Samples every 100 m; a contiguous unpaved run (indices 3..6) -> one span,
    # a single-sample blip is dropped as noise.
    sample_m = [i * 100.0 for i in range(12)]
    unpaved = [False, False, False, True, True, True, True, False, False, True, False, False]
    spans = _unpaved_spans(sample_m, unpaved, spacing_m=100.0)
    assert len(spans) == 1
    assert spans[0].kind == SpanKind.UNPAVED
    assert spans[0].start_mile < spans[0].end_mile


def test_detect_pois_includes_all_named_waypoints():
    # All named waypoints become POIs regardless of fuel/food hints; only unnamed
    # waypoints are dropped.
    from gpxsheet.analysis import detect_pois
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, POIKind, Route, Waypoint

    pts = [GeoPoint(0.0, i * 0.01) for i in range(6)]
    route = Route(
        name="w", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        waypoints=[
            Waypoint(0.0, 0.0, "Start Overlook", None),
            Waypoint(0.0, 0.02, "Joe's Diner", "Restaurant"),
            Waypoint(0.0, 0.04, "Shell Station", "Gas Station"),  # fuel hint: now included
            Waypoint(0.0, 0.05, None, None),  # unnamed -> still skipped
        ],
    )
    pois = detect_pois(route)
    names = {p.name: p.kind for p in pois}
    assert names == {
        "Start Overlook": POIKind.WAYPOINT,
        "Joe's Diner": POIKind.FOOD,
        "Shell Station": POIKind.WAYPOINT,
    }


def test_detect_pois_drops_off_route_waypoint():
    # A named waypoint far to the side of the route is off-route and dropped,
    # rather than snapped to the nearest endpoint (which would stack it on a slice).
    from gpxsheet.analysis import detect_pois
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, Route, Waypoint

    pts = [GeoPoint(37.0, i * 0.01) for i in range(6)]  # ~3.4 mi due east
    route = Route(
        name="w", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        waypoints=[
            Waypoint(37.0, 0.02, "On Route", None),  # right on the line -> kept
            Waypoint(37.05, 0.02, "Way Off", None),  # ~3.4 mi north -> dropped
        ],
    )
    names = {p.name for p in detect_pois(route)}
    assert names == {"On Route"}


def test_detect_fuel_stops_drops_off_route():
    from gpxsheet.analysis import detect_fuel_stops
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, Route, Waypoint

    pts = [GeoPoint(37.0, i * 0.01) for i in range(6)]
    route = Route(
        name="w", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        waypoints=[
            Waypoint(37.0, 0.03, "Shell", "Gas Station"),  # on route -> kept
            Waypoint(37.05, 0.03, "Far Gas", "Gas Station"),  # off route -> dropped
        ],
    )
    stops = detect_fuel_stops(route)
    assert [s.name for s in stops] == ["Shell"]
    assert 0.0 < stops[0].mile < route.length_miles  # sensible interpolated mile


def test_continue_onto_residential_is_down_weighted():
    # A straight name change onto a minor residential road is penalized below the
    # sport-touring threshold; arterials and highways keep full weight.
    from gpxsheet.enrich import _road_change_significance
    from gpxsheet.profiles import SCORE_ROAD_NAME_CHANGE, get_profile

    threshold = get_profile("sport-touring").decision_threshold
    cul_de_sac = _road_change_significance("Toro Court", angle=2.0)
    assert cul_de_sac < SCORE_ROAD_NAME_CHANGE
    assert cul_de_sac < threshold  # filtered out as noise
    # A sharp turn onto the same minor road is a real decision -> full weight.
    assert _road_change_significance("Toro Court", angle=80.0) >= threshold
    # A straight continue onto an arterial or a numbered highway is not penalized.
    assert _road_change_significance("Sand Hill Road", angle=2.0) >= threshold
    assert _road_change_significance("US-101", angle=2.0) >= threshold


def test_durable_runs_deadband_keeps_borderline_run():
    # A 3-sample interior run spans 200 m between its first/last sample, but the
    # one-spacing pad credits it 300 m so a run sitting on the 250 m threshold is
    # kept (and stays kept regardless of sampling phase), instead of flapping.
    from gpxsheet.enrich import _durable_runs

    sample_m = [i * 100.0 for i in range(11)]  # 0..1000 m
    names = ["Main St"] * 4 + ["Side Rd"] * 3 + ["Main St"] * 4
    road_names = [r.name for r in _durable_runs(sample_m, names, min_run_m=250.0)]
    assert road_names == ["Main St", "Side Rd", "Main St"]


def test_roundabout_exit_count_on_real_route(roundabout_route_file):
    # The route goes straight through the La Loma Ave roundabout -> the 2nd exit.
    # A one-way feeder at the ring used to inflate this to the 3rd exit.
    from gpxsheet import load_route
    from gpxsheet.analysis import analyze_route
    from gpxsheet.models import DecisionKind

    route = load_route(str(roundabout_route_file))
    analyze_route(route, profile="sport-touring")
    roundabouts = [d for d in route.decision_points if d.kind == DecisionKind.ROUNDABOUT]
    assert len(roundabouts) == 1
    rd = roundabouts[0]
    assert rd.roundabout_exit == 2
    assert rd.instruction == "Take the 2nd exit onto La Loma Avenue"


def test_drive_service_fallback_enriches_remote_road(mthamilton_route_file):
    # Plain network_type="drive" returns no graph nodes on this remote clip;
    # the drive_service fallback must still resolve the real road names instead
    # of degrading to the geometry baseline ("Leg N" segments).
    from gpxsheet import load_route
    from gpxsheet.analysis import analyze_route

    route = load_route(str(mthamilton_route_file))
    analyze_route(route, profile="sport-touring")
    assert route.segments
    assert all(not s.name.startswith("Leg ") for s in route.segments)
    names = " ".join(s.name for s in route.segments)
    assert "Mount Hamilton Road" in names or "San Antonio Valley Road" in names


def test_chunk_ranges_tile_with_shared_boundaries():
    from gpxsheet.enrich import _chunk_ranges
    from gpxsheet.models import GeoPoint, Route

    pts = [GeoPoint(0.0, i * 0.01) for i in range(20)]  # 20 points
    dists = [i * 1000.0 for i in range(20)]  # 1 km apart
    route = Route(name="x", points=pts, distances_m=dists)

    chunks = _chunk_ranges(route, max_points=5, max_miles=1e9)
    # cover the whole route, in order
    assert chunks[0][0] == 0
    assert chunks[-1][1] == 19
    # consecutive chunks share their boundary point (no sampling gap)
    for (_, end), (start2, _) in zip(chunks, chunks[1:], strict=False):
        assert end == start2
    # each chunk respects the point cap (inclusive range -> <= max_points spans)
    assert all(i1 - i0 <= 5 for i0, i1 in chunks)


def test_chunk_ranges_respects_mileage():
    from gpxsheet.enrich import _chunk_ranges
    from gpxsheet.models import GeoPoint, Route

    pts = [GeoPoint(0.0, i * 0.01) for i in range(40)]
    dists = [i * 1609.344 for i in range(40)]  # 1 mile apart
    route = Route(name="x", points=pts, distances_m=dists)
    chunks = _chunk_ranges(route, max_points=10_000, max_miles=10.0)
    assert all((dists[i1] - dists[i0]) <= 10 * 1609.344 + 1 for i0, i1 in chunks)
    assert chunks[-1][1] == 39


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


class _FakeOx:
    """Minimal stand-in for osmnx returning canned ferry features."""

    def __init__(self, feats):
        self._feats = feats

    def features_from_polygon(self, poly, tags):  # noqa: ARG002 (signature match)
        return self._feats


def _ferry_feats(geoms, names):
    import geopandas as gpd

    return gpd.GeoDataFrame({"name": names}, geometry=geoms)


def _vertical_route():
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, Route

    # Runs north along lon=0 from lat 0.0 to 0.1, sampled finely.
    pts = [GeoPoint(round(i * 0.01, 3), 0.0) for i in range(11)]
    return Route(
        name="t", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
    )


def test_detect_ferries_ignores_passed_terminal():
    import shapely.geometry as sg

    from gpxsheet.enrich import _detect_ferries

    # A long ferry that merely crosses the route once (riding past its terminal).
    passing = sg.LineString([(0.0, 0.05), (0.2, 0.05)])
    feats = _ferry_feats([passing], ["Bay Ferry"])
    assert _detect_ferries(_vertical_route(), _FakeOx(feats), sg, buffer_m=50.0) == []


def test_detect_ferries_reports_ride_along_span():
    import shapely.geometry as sg

    from gpxsheet.enrich import _detect_ferries
    from gpxsheet.models import SpanKind

    # A ferry the route rides along (coincides with the route corridor).
    along = sg.LineString([(0.0, 0.02), (0.0, 0.08)])
    feats = _ferry_feats([along], ["River Ferry"])
    spans = _detect_ferries(_vertical_route(), _FakeOx(feats), sg, buffer_m=50.0)
    assert len(spans) == 1
    s = spans[0]
    assert s.kind == SpanKind.FERRY
    assert s.name == "River Ferry"
    assert s.end_mile > s.start_mile  # covers a real mile range, not a point


def test_enrich_route_against_cached_osm(enrich_route_file):
    from gpxsheet import load_route
    from gpxsheet.analysis import analyze_route

    route = load_route(str(enrich_route_file))
    analyze_route(route, profile="sport-touring")
    # Segments should be real OSM road names, not generic "Leg N".
    assert route.segments
    assert all(not s.name.startswith("Leg ") for s in route.segments)
    # Decisions come from road-name changes -> every instruction names a road.
    assert route.decision_points
    assert all("onto" in d.instruction for d in route.decision_points)
    # The point of the tuning: decisions track real road changes, not the road's
    # curvature, so the count stays bounded (no per-curve flood).
    assert len(route.decision_points) / route.length_miles < 1.0


def test_fuel_query_failure_keeps_osm_enrichment(enrich_route_file, monkeypatch):
    """A late OSM fuel failure must not discard the road-name enrichment.

    Regression: ``_add_fuel`` raising (e.g. a transient Overpass outage) used to
    propagate out of ``enrich_route`` and make ``_osm_enrich_pass`` report
    geometry-only -- even though decisions/segments were already OSM-derived.
    """
    from gpxsheet import enrich as enrich_mod
    from gpxsheet import load_route
    from gpxsheet.analysis import analyze_route

    def _boom(*_a, **_k):
        raise RuntimeError("overpass down")

    monkeypatch.setattr(enrich_mod, "_add_fuel", _boom)
    route = load_route(str(enrich_route_file))
    analyze_route(route, profile="sport-touring")  # must not raise
    # Road-name segments/decisions survive -> the route is still OSM-enriched.
    assert route.segments and all(not s.name.startswith("Leg ") for s in route.segments)
    assert route.decision_points and all("onto" in d.instruction for d in route.decision_points)
