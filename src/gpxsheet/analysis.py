"""The route analysis engine.

Geometry-only baseline for the pipeline stages in docs/product.md:

    Geometry Cleanup -> Decision Point Detection
                     -> Reassurance Marker Detection
                     -> Fuel Analysis
                     -> (light) Segmentation

Road names, intersection classification and fuel-station discovery come from OSM
enrichment (see :mod:`gpxsheet.enrich`), which is optional. Without it, decision
points are detected purely from track geometry (localized heading changes) and
fuel comes from GPX waypoints that look like fuel stops.
"""

from __future__ import annotations

import logging
import os
import warnings
from dataclasses import replace

from .geo import bearing, bearing_delta, meters_to_miles, miles_to_meters, project_to_segment
from .models import (
    POI,
    DecisionKind,
    DecisionPoint,
    FuelReport,
    FuelStop,
    GeoPoint,
    POIKind,
    ReassuranceMarker,
    Route,
    Segment,
)
from .profiles import Profile, get_profile
from .simplify import rdp

log = logging.getLogger(__name__)

# Cleanup tolerance: strip GPS jitter before bearing analysis.
CLEANUP_TOLERANCE_M = 10.0
# A turn must accumulate at least this much heading change to count.
TURN_ANGLE_THRESHOLD_DEG = 35.0
# ...and do so within this arc length, so sweeping curves (large radius) are
# excluded while junction-style turns (tight radius) are kept.
MAX_TURN_ARC_M = 90.0
# Heading change below this at a vertex is treated as "straight" (breaks a run).
STRAIGHT_EPS_DEG = 8.0
# Suppress a reassurance marker only if it falls this close to the route end
# (where it would be redundant with arrival). Small and fixed so a marker that
# is genuinely far from the end is never dropped.
END_MARKER_BUFFER_MILES = 0.5
# Decision points closer than this do not each start a new segment (avoids
# degenerate zero-length legs from clustered turns on noisy recorded tracks).
MIN_SEGMENT_MILES = 0.1
# Decision points within this distance of each other are collapsed into one
# (real recorded tracks produce tight clusters at complex intersections).
MERGE_MIN_SEPARATION_MILES = 0.2
# OSM decision detection: a road name must hold for at least this distance to
# count as a real road (filters nearest-edge flapping at junctions). Tuned
# against real tracks (see git history / tests).
MIN_ROAD_RUN_MILES = 0.3
# A road-name change with a heading change below this reads as "Continue onto",
# not "Left/Right onto".
CONTINUE_MAX_ANGLE_DEG = 25.0
# A named GPX waypoint farther than this (perpendicular) from the route is
# treated as off-route and dropped, rather than snapped to the nearest endpoint
# (cf. _label_near's 1.0 mi cap). Distant waypoints would otherwise project to
# whatever vertex is closest and stack on the start/end of a sub-route slice.
MAX_WAYPOINT_OFFSET_MILES = 1.0
# Below this point density the geometry is too sparse to follow roads (e.g. a
# waypoint-only <rte> with long straight legs); OSM road-name sampling along such
# straight lines snaps to whatever streets it crosses, so we skip enrichment.
MIN_POINTS_PER_MILE_FOR_OSM = 1.0


def looks_sparse(route: Route) -> bool:
    """True if the route geometry is too sparse for reliable OSM enrichment.

    Sparse routes (few points over long distances, e.g. device ``<rte>`` exports)
    are drawn as straight lines between waypoints that do not follow real roads,
    so sampling OSM road names along them is meaningless.
    """
    if route.length_miles <= 0:
        return False
    return len(route.points) / route.length_miles < MIN_POINTS_PER_MILE_FOR_OSM

# Fuel-stop detection from waypoint names/symbols when OSM is unavailable.
_FUEL_HINTS = ("fuel", "gas", "petrol", "station", "shell", "chevron", "76", "arco")
# Food / rest-stop detection from waypoint names/symbols.
_FOOD_HINTS = (
    "restaurant", "cafe", "café", "diner", "food", "grill", "bbq", "coffee",
    "deli", "pizza", "taqueria", "taco", "brewery", "brewpub", "pub", "bakery",
    "lunch", "breakfast", "eatery", "fast food",
)


def turn_word(total_angle: float) -> str:
    direction = "Right" if total_angle > 0 else "Left"
    if abs(total_angle) >= 100.0:
        return f"Sharp {direction.lower()}"
    return direction


def significance_for_turn(total_angle: float) -> int:
    mag = abs(total_angle)
    if mag >= 100.0:
        return 80
    if mag >= 60.0:
        return 60
    return 45


def coord_at_meters(route: Route, meters: float) -> tuple[float, float]:
    """(lat, lon) interpolated along the route at a given along-track distance.

    Linear interpolation between the two bracketing vertices, so results are
    accurate even on sparsely sampled routes (important for measuring turn
    angles around a point).
    """
    dist = route.distances_m
    target = max(0.0, min(meters, dist[-1]))
    hi = 1
    lo_b, hi_b = 1, len(dist) - 1
    while lo_b < hi_b:
        mid = (lo_b + hi_b) // 2
        if dist[mid] < target:
            lo_b = mid + 1
        else:
            hi_b = mid
    hi = lo_b
    lo = hi - 1
    span = dist[hi] - dist[lo]
    f = 0.0 if span <= 0 else (target - dist[lo]) / span
    a, b = route.points[lo], route.points[hi]
    return a.lat + f * (b.lat - a.lat), a.lon + f * (b.lon - a.lon)


def turn_angle_at_mile(route: Route, mile: float, window_m: float = 50.0) -> float:
    """Signed heading change of the route across a point (+right / -left).

    Compares the bearing approaching ``mile`` with the bearing departing it,
    sampled ``window_m`` either side. Used to give an OSM road-name-change
    decision its turn direction.
    """
    center_m = miles_to_meters(mile)
    before = coord_at_meters(route, center_m - window_m)
    at = coord_at_meters(route, center_m)
    after = coord_at_meters(route, center_m + window_m)
    approach = bearing(before[0], before[1], at[0], at[1])
    depart = bearing(at[0], at[1], after[0], after[1])
    return bearing_delta(approach, depart)


def merge_close_decisions(
    decisions: list[DecisionPoint], min_separation_miles: float = MERGE_MIN_SEPARATION_MILES
) -> list[DecisionPoint]:
    """Collapse decisions closer than ``min_separation_miles`` into one each.

    The representative of a cluster is its highest-significance member (ties
    broken by sharpest turn), so the rider gets one prompt for a complex
    intersection instead of several.
    """
    if min_separation_miles <= 0 or len(decisions) < 2:
        return list(decisions)
    ordered = sorted(decisions, key=lambda d: d.mile)
    merged: list[DecisionPoint] = []
    cluster: list[DecisionPoint] = [ordered[0]]
    for d in ordered[1:]:
        if d.mile - cluster[-1].mile <= min_separation_miles:
            cluster.append(d)
        else:
            merged.append(_pick_representative(cluster))
            cluster = [d]
    merged.append(_pick_representative(cluster))
    return merged


def _pick_representative(cluster: list[DecisionPoint]) -> DecisionPoint:
    return max(cluster, key=lambda d: (d.significance, abs(d.turn_angle or 0.0)))


def detect_decision_points(points: list[GeoPoint]) -> list[DecisionPoint]:
    """Detect localized turns from cleaned geometry.

    Consecutive same-direction heading changes are grouped into a single turn;
    a group qualifies as a decision when its total heading change exceeds
    :data:`TURN_ANGLE_THRESHOLD_DEG` within :data:`MAX_TURN_ARC_M`.
    """
    clean = rdp(points, CLEANUP_TOLERANCE_M)
    if len(clean) < 3:
        return []

    bearings = [
        bearing(clean[i].lat, clean[i].lon, clean[i + 1].lat, clean[i + 1].lon)
        for i in range(len(clean) - 1)
    ]
    # Turn angle at interior vertex i (1..len-2) is delta between leg i-1 and leg i.
    deltas = [bearing_delta(bearings[i - 1], bearings[i]) for i in range(1, len(bearings))]

    # Recompute cumulative distance on the cleaned geometry.
    from .geo import cumulative_distances

    clean_dist = cumulative_distances([(p.lat, p.lon) for p in clean])

    decisions: list[DecisionPoint] = []
    run: list[int] = []  # indices into `clean` (vertex index = delta index + 1)

    def flush(run_idx: list[int]) -> None:
        if not run_idx:
            return
        total = sum(deltas[v - 1] for v in run_idx)
        if abs(total) >= TURN_ANGLE_THRESHOLD_DEG:
            apex = max(run_idx, key=lambda v: abs(deltas[v - 1]))
            decisions.append(
                DecisionPoint(
                    mile=meters_to_miles(clean_dist[apex]),
                    instruction=turn_word(total),
                    significance=significance_for_turn(total),
                    lat=clean[apex].lat,
                    lon=clean[apex].lon,
                    kind=DecisionKind.CRITICAL_TURN,
                    turn_angle=round(total, 1),
                )
            )

    # Group consecutive heading changes that are part of the *same* corner: same
    # turn direction and confined to a short arc. After geometry cleanup, a long
    # straight (or a separate corner farther along) appears as a far-apart vertex,
    # which breaks the run so each corner is detected independently. A genuine
    # sweeping curve spreads its heading change over a long arc, so its per-vertex
    # deltas stay below the threshold and it is not flagged.
    sign = 0
    for vtx in range(1, len(clean) - 1):
        d = deltas[vtx - 1]
        if abs(d) < STRAIGHT_EPS_DEG:
            flush(run)
            run, sign = [], 0
            continue
        d_sign = 1 if d > 0 else -1
        too_far = bool(run) and (clean_dist[vtx] - clean_dist[run[0]]) > MAX_TURN_ARC_M
        if run and (d_sign != sign or too_far):
            flush(run)
            run = []
        sign = d_sign
        run.append(vtx)
    flush(run)

    decisions.sort(key=lambda d: d.mile)
    return decisions


def generate_reassurance_markers(
    route: Route, interval_miles: float
) -> list[ReassuranceMarker]:
    """Place a marker every ``interval_miles``, labeled by the nearest waypoint."""
    if interval_miles <= 0 or route.length_miles <= interval_miles:
        return []

    markers: list[ReassuranceMarker] = []
    mile = interval_miles
    while mile < route.length_miles - END_MARKER_BUFFER_MILES:
        idx = _index_at_mile(route, mile)
        pt = route.points[idx]
        label, reason = _label_near(route, idx)
        markers.append(
            ReassuranceMarker(
                mile=round(mile, 1), label=label, lat=pt.lat, lon=pt.lon, reason=reason
            )
        )
        mile += interval_miles
    return markers


def _index_at_mile(route: Route, mile: float) -> int:
    target_m = miles_to_meters(mile)
    # distances_m is sorted ascending.
    lo, hi = 0, len(route.distances_m) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if route.distances_m[mid] < target_m:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _label_near(route: Route, idx: int, max_miles: float = 1.0) -> tuple[str, str]:
    """Best label for a point: nearest named waypoint, else the mileage.

    Waypoints with a name are always shown as dedicated POI markers, so they are
    excluded here to avoid a duplicate reassurance label at the same location.
    """
    pt = route.points[idx]
    best_name, best_d = None, miles_to_meters(max_miles)
    from .geo import haversine

    poi_miles = {p.mile for p in route.pois}

    for wp in route.waypoints:
        if not wp.name:
            continue
        mile, _ = _project_to_route(route, wp.lat, wp.lon)
        if mile in poi_miles:
            continue  # already shown as a POI marker
        d = haversine(pt.lat, pt.lon, wp.lat, wp.lon)
        if d < best_d:
            best_name, best_d = wp.name, d
    if best_name:
        return best_name, "landmark"
    return f"{meters_to_miles(route.distances_m[idx]):.0f} mi", "interval"


def _project_to_route(route: Route, lat: float, lon: float) -> tuple[float, float]:
    """``(mile, cross_track_m)``: nearest point on the route polyline to a point.

    Cross-track distance is computed in a local equirectangular frame centered on
    the point (accurate for the short offsets that matter here); the mile is
    interpolated along the nearest segment rather than snapped to a vertex, so a
    waypoint mid-way along a long leg on a sparse route reads correctly.
    """
    from .geo import haversine

    pts = route.points
    if len(pts) < 2:
        d = haversine(pts[0].lat, pts[0].lon, lat, lon) if pts else float("inf")
        return 0.0, d

    best_d, best_mile = float("inf"), 0.0
    for i in range(len(pts) - 1):
        d, t = project_to_segment(
            lat, lon, (pts[i].lat, pts[i].lon), (pts[i + 1].lat, pts[i + 1].lon)
        )
        if d < best_d:
            d_a, d_b = route.distances_m[i], route.distances_m[i + 1]
            best_mile = meters_to_miles(d_a + t * (d_b - d_a))
            best_d = d
    return round(best_mile, 1), best_d


def _looks_like_fuel(wp_name: str | None, wp_symbol: str | None) -> bool:
    haystack = f"{wp_name or ''} {wp_symbol or ''}".lower()
    return any(h in haystack for h in _FUEL_HINTS)


def _looks_like_food(wp_name: str | None, wp_symbol: str | None) -> bool:
    haystack = f"{wp_name or ''} {wp_symbol or ''}".lower()
    return any(h in haystack for h in _FOOD_HINTS)


def detect_pois(route: Route) -> list[POI]:
    """Project named GPX waypoints onto the route for display on the strip.

    All rider waypoints (``<wpt>``) become POI markers regardless of whether they
    mention fuel or food — the rider's explicit mark takes priority over OSM
    enrichment in the same area. Food/rest stops are tagged so the renderer gives
    them their own glyph. Each waypoint is projected to the nearest point on the
    route for a mileage estimate; one farther than
    :data:`MAX_WAYPOINT_OFFSET_MILES` (perpendicular) is treated as off-route and
    dropped rather than snapped to the closest endpoint.
    """
    max_off_m = miles_to_meters(MAX_WAYPOINT_OFFSET_MILES)
    pois: list[POI] = []
    for wp in route.waypoints:
        if not wp.name:
            continue
        mile, off_m = _project_to_route(route, wp.lat, wp.lon)
        if off_m > max_off_m:
            continue
        kind = POIKind.FOOD if _looks_like_food(wp.name, wp.symbol) else POIKind.WAYPOINT
        pois.append(
            POI(mile=mile, name=wp.name, lat=wp.lat, lon=wp.lon, kind=kind, symbol=wp.symbol)
        )
    pois.sort(key=lambda p: p.mile)
    return pois


def detect_fuel_stops(route: Route) -> list[FuelStop]:
    """Find fuel stops from GPX waypoints (OSM enrichment supersedes this)."""
    max_off_m = miles_to_meters(MAX_WAYPOINT_OFFSET_MILES)
    stops: list[FuelStop] = []
    for wp in route.waypoints:
        if not _looks_like_fuel(wp.name, wp.symbol):
            continue
        # Project onto the route; drop a waypoint that is not actually near it.
        mile, off_m = _project_to_route(route, wp.lat, wp.lon)
        if off_m > max_off_m:
            continue
        stops.append(FuelStop(mile=mile, name=wp.name or "Fuel", lat=wp.lat, lon=wp.lon))
    stops.sort(key=lambda s: s.mile)
    return stops


def analyze_fuel(route: Route, fuel_range: float | None) -> FuelReport:
    """Longest fuel gap and range warning, given detected fuel stops."""
    stops = route.fuel_stops
    miles = [0.0] + [s.mile for s in stops] + [route.length_miles]
    gaps = [b - a for a, b in zip(miles, miles[1:], strict=False)]
    longest = max(gaps) if gaps else route.length_miles
    return FuelReport(
        longest_gap_miles=round(longest, 1),
        recommended=[s.name for s in stops],
        exceeds_range=bool(fuel_range and longest > fuel_range),
        fuel_range_miles=fuel_range,
    )


def build_segments(route: Route) -> list[Segment]:
    """Split the route into legs between decision points.

    Decision points closer together than :data:`MIN_SEGMENT_MILES` (e.g. the
    tight clusters real recorded tracks produce at complex intersections) do not
    each start a new leg, so no degenerate zero-length segments are emitted.
    Legs are numbered sequentially ("Leg N"); enrichment renames them to the
    dominant road name for each leg.
    """
    boundaries = [0.0] + [d.mile for d in route.decision_points] + [route.length_miles]
    boundaries = sorted({round(b, 3) for b in boundaries})
    segments: list[Segment] = []
    start = boundaries[0]
    for end in boundaries[1:]:
        if end - start < MIN_SEGMENT_MILES:
            continue  # too short to be its own leg; fold into the next boundary
        segments.append(
            Segment(
                name=f"Leg {len(segments) + 1}",
                start_mile=round(start, 1),
                end_mile=round(end, 1),
            )
        )
        start = end
    # Extend the final leg to the route end if a trailing sliver was folded in.
    if segments and segments[-1].end_mile < round(route.length_miles, 1):
        segments[-1] = replace(segments[-1], end_mile=round(route.length_miles, 1))
    return segments


def _geometry_baseline(route: Route) -> None:
    """Step 1: populate decisions/segments from geometry alone.

    On twisty roads this over-detects (curves look like turns). OSM enrichment
    in the next step replaces these with junction/road-name decisions when
    available, so this is only the final answer on sparse/offline routes.
    """
    route.decision_points = merge_close_decisions(detect_decision_points(route.points))
    route.fuel_stops = []  # populated by OSM enrichment; GPX fuel waypoints shown as POIs
    route.segments = build_segments(route)


def _osm_enrich_pass(
    route: Route, prof: Profile, include_hazards: bool, osm: bool = True
) -> bool:
    """Step 2: replace geometry decisions with OSM road-name decisions.

    Skips sparse routes (waypoint-only <rte>) and falls back gracefully on any
    Overpass/network failure. Returns True if OSM ran successfully. ``osm=False``
    skips enrichment outright (a caller-level opt-out, like the env var but
    without a warning), keeping a fast, fully offline analysis.
    """
    from .enrich import enrich_route

    if not osm:
        return False
    if os.getenv("GPXSHEET_DISABLE_OSM", "").lower() in ("1", "true", "yes"):
        # Opt-out for air-gapped / Overpass-rate-limited deployments (and CI smoke
        # tests): skip enrichment entirely, with no network call, and use the
        # geometry-only baseline. Consistent with enrich._configure_osm_cache.
        warnings.warn(
            "OSM enrichment disabled (GPXSHEET_DISABLE_OSM); "
            "using geometry-only analysis.",
            stacklevel=3,
        )
        return False
    if looks_sparse(route):
        warnings.warn(
            "Route geometry is sparse (likely a waypoint-only <rte>); skipping "
            "OSM enrichment, which would sample road names along straight lines "
            "that do not follow roads. Using geometry-only analysis.",
            stacklevel=3,
        )
        return False
    try:
        enrich_route(route, include_fuel=prof.include_fuel, include_hazards=include_hazards)
        return True
    except Exception as exc:  # network/Overpass/data failure -> fall back
        log.exception("OSM enrichment failed; using geometry-only analysis")
        warnings.warn(
            f"OSM enrichment failed ({type(exc).__name__}: {exc}); "
            "using geometry-only analysis.",
            stacklevel=3,
        )
        return False


def _apply_profile(
    route: Route, prof: Profile, fuel_range: float | None, osm_ran: bool
) -> None:
    """Step 3: apply profile threshold and derive fuel/reassurance products."""
    # Geometry-only fallback: GPX waypoints are the fuel source since OSM didn't run.
    if not osm_ran and prof.include_fuel:
        route.fuel_stops = detect_fuel_stops(route)

    route.decision_points = [
        d for d in route.decision_points if d.significance >= prof.decision_threshold
    ]
    route.fuel_report = analyze_fuel(route, fuel_range) if prof.include_fuel else None
    route.pois = detect_pois(route) if prof.include_reassurance else []
    route.reassurance_markers = (
        generate_reassurance_markers(route, prof.reassurance_interval_miles)
        if prof.include_reassurance else []
    )


def analyze_route(
    route: Route,
    *,
    profile: str | Profile = "sport-touring",
    fuel_range: float | None = None,
    include_hazards: bool = False,
    osm: bool = True,
) -> Route:
    """Run the full analysis, populating ``route`` in place.

    Decisions and segments come from OSM road topology (durable road-name changes,
    named roads), falling back to the geometry baseline (with a warning) when the
    route is too sparse to sample or the Overpass query fails. ``include_hazards``
    adds OSM hazard data (ferry crossings; unpaved mileage is captured whenever the
    OSM pass runs) for :func:`gpxsheet.validate.validate_route`. ``osm=False``
    forces a fast, fully offline geometry-only analysis. Returns the same
    :class:`Route` for convenience.
    """
    prof = profile if isinstance(profile, Profile) else get_profile(profile)
    _geometry_baseline(route)
    osm_ran = _osm_enrich_pass(route, prof, include_hazards, osm)
    _apply_profile(route, prof, fuel_range, osm_ran)
    return route
