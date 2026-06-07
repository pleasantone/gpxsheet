"""The route analysis engine — Milestone 1.

Geometry-only baseline for the pipeline stages in PRODUCT.md:

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

from .geo import bearing, bearing_delta, meters_to_miles
from .models import (
    DecisionKind,
    DecisionPoint,
    FuelReport,
    FuelStop,
    GeoPoint,
    ReassuranceMarker,
    Route,
    Segment,
)
from .profiles import Profile, get_profile
from .simplify import rdp

# Cleanup tolerance: strip GPS jitter before bearing analysis.
CLEANUP_TOLERANCE_M = 10.0
# A turn must accumulate at least this much heading change to count.
TURN_ANGLE_THRESHOLD_DEG = 35.0
# ...and do so within this arc length, so sweeping curves (large radius) are
# excluded while junction-style turns (tight radius) are kept.
MAX_TURN_ARC_M = 90.0
# Heading change below this at a vertex is treated as "straight" (breaks a run).
STRAIGHT_EPS_DEG = 8.0

# Fuel-stop detection from waypoint names/symbols when OSM is unavailable.
_FUEL_HINTS = ("fuel", "gas", "petrol", "station", "shell", "chevron", "76", "arco")


def _turn_word(total_angle: float) -> str:
    direction = "Right" if total_angle > 0 else "Left"
    if abs(total_angle) >= 100.0:
        return f"Sharp {direction.lower()}"
    return direction


def _significance_for_turn(total_angle: float) -> int:
    mag = abs(total_angle)
    if mag >= 100.0:
        return 80
    if mag >= 60.0:
        return 60
    return 45


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
                    instruction=_turn_word(total),
                    significance=_significance_for_turn(total),
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
    while mile < route.length_miles - 0.5 * interval_miles:
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
    target_m = mile * 1609.344
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
    """Best label for a point: nearest named waypoint, else the mileage."""
    pt = route.points[idx]
    best_name, best_d = None, max_miles * 1609.344
    from .geo import haversine

    for wp in route.waypoints:
        if not wp.name:
            continue
        d = haversine(pt.lat, pt.lon, wp.lat, wp.lon)
        if d < best_d:
            best_name, best_d = wp.name, d
    if best_name:
        return best_name, "landmark"
    return f"{meters_to_miles(route.distances_m[idx]):.0f} mi", "interval"


def _looks_like_fuel(wp_name: str | None, wp_symbol: str | None) -> bool:
    haystack = f"{wp_name or ''} {wp_symbol or ''}".lower()
    return any(h in haystack for h in _FUEL_HINTS)


def detect_fuel_stops(route: Route) -> list[FuelStop]:
    """Find fuel stops from GPX waypoints (OSM enrichment supersedes this)."""
    stops: list[FuelStop] = []
    from .geo import haversine

    for wp in route.waypoints:
        if not _looks_like_fuel(wp.name, wp.symbol):
            continue
        # Project waypoint onto route by nearest vertex for a mileage estimate.
        nearest = min(
            range(len(route.points)),
            key=lambda i: haversine(route.points[i].lat, route.points[i].lon, wp.lat, wp.lon),
        )
        stops.append(
            FuelStop(
                mile=round(meters_to_miles(route.distances_m[nearest]), 1),
                name=wp.name or "Fuel",
                lat=wp.lat,
                lon=wp.lon,
            )
        )
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

    Without OSM road names these are generic ("Leg N"); enrichment renames them
    to the dominant road name for each leg.
    """
    boundaries = [0.0] + [d.mile for d in route.decision_points] + [route.length_miles]
    boundaries = sorted({round(b, 3) for b in boundaries})
    segments: list[Segment] = []
    pairs = zip(boundaries, boundaries[1:], strict=False)
    for i, (start, end) in enumerate(pairs, start=1):
        if end - start <= 0.0:
            continue
        segments.append(
            Segment(name=f"Leg {i}", start_mile=round(start, 1), end_mile=round(end, 1))
        )
    return segments


def analyze_route(
    route: Route,
    *,
    profile: str | Profile = "sport-touring",
    fuel_range: float | None = None,
    reassurance_interval: float | None = None,
    use_osm: bool = False,
) -> Route:
    """Run the full Milestone 1 analysis, populating ``route`` in place.

    Returns the same :class:`Route` for convenience.
    """
    prof = profile if isinstance(profile, Profile) else get_profile(profile)
    interval = (
        reassurance_interval
        if reassurance_interval is not None
        else prof.reassurance_interval_miles
    )

    if use_osm:
        from .enrich import enrich_route

        enrich_route(route)

    detected = detect_decision_points(route.points)
    route.decision_points = [d for d in detected if d.significance >= prof.decision_threshold]

    route.fuel_stops = detect_fuel_stops(route) if prof.include_fuel else []
    route.fuel_report = analyze_fuel(route, fuel_range) if prof.include_fuel else None

    route.reassurance_markers = (
        generate_reassurance_markers(route, interval) if prof.include_reassurance else []
    )
    route.segments = build_segments(route)
    return route
