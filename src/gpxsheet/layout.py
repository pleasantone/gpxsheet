"""Schematic Layout Engine.

Turns the analyzed :class:`~gpxsheet.models.Route` graph into a *schematic* strip
-- not a plot of the GPX. Following docs/product.md's "Hybrid Schematic Map System":

* the route is drawn as a ribbon that jogs at each decision (preserving turn
  *direction* and rough character, transit-map style), not the literal track,
* segment visual length is compressed (sub-linear in real distance) so long
  uninterrupted roads don't dominate and short/complex stretches stay legible,
* turns are quantized/exaggerated into a few stylized angles for readability.

The engine is pure geometry/data (no matplotlib), so it is fully unit-testable;
:mod:`gpxsheet.strip` renders the resulting layout to an image.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import Branch, DecisionKind, DecisionPoint, Route, RouteSpan, Segment

# Schematic sizing (arbitrary units; the renderer scales to fit). A larger floor
# plus a gentler distance term makes segment lengths more uniform -- short
# segments get enough room for their labels, long roads stay compressed
# (information density matters more than raw distance, per docs/product.md).
MIN_SEGMENT_LEN = 2.6  # every segment gets at least this much strip, however short
DIST_SCALE = 1.0  # multiplies sqrt(miles); sub-linear compression of long roads

# Two ways to bend the ribbon at a turn:
#   "stylized" (default): quantize to a few exaggerated angles by sharpness, so
#       the strip reads like a transit map (docs/product.md: "exaggerates important
#       junctions", "improves readability").
#   "faithful": bend by the route's actual turn angle (a 90-degree turn bends
#       the line ~90 degrees), capped so a hairpin doesn't fold over the line.
TURN_STYLE_STYLIZED = "stylized"
TURN_STYLE_FAITHFUL = "faithful"
TURN_STYLES = (TURN_STYLE_STYLIZED, TURN_STYLE_FAITHFUL)

# Stylized magnitudes (degrees) by turn sharpness. Kept modest so the strip
# flows left-to-right and doesn't curl, while a sharp turn still reads as sharp.
CONTINUE_TURN_DEG = 10.0  # road-name change with little/no heading change
NORMAL_TURN_DEG = 30.0
SHARP_TURN_DEG = 55.0
# Faithful mode caps a single bend so hairpins don't fold back over the line.
MAX_BEND_DEG = 150.0
# Stylized turns accumulate heading; a run of same-direction turns would spiral
# the ribbon (it stops reading left-to-right and can fold over itself). After
# each stylized bend the heading is relaxed toward horizontal by this fraction,
# bounding the cumulative drift while keeping every individual turn visible.
CURL_RELAX = 0.25
MARKER_MATCH_TOLERANCE_MILES = 0.15

# A non-decision marker (fuel/reassurance/waypoint) landing on the START or END
# node is nudged this far along the ribbon so its dot/label clears the endpoint
# marker. Schematic units; ~half a minimum segment keeps it visually adjacent.
END_CLEAR_DIST = MIN_SEGMENT_LEN * 0.5


@dataclass(frozen=True, slots=True)
class PlacedMarker:
    """A marker positioned in schematic strip coordinates."""

    x: float
    y: float
    mile: float
    kind: str  # start | end | decision | roundabout | fuel | reassurance
    label: str
    significance: int = 0
    instruction: str | None = None
    branches: tuple[Branch, ...] = ()  # roads NOT taken, for ghosted stubs
    roundabout_exit: int | None = None
    symbol: str | None = None  # GPX <sym> tag, for waypoint glyph selection


@dataclass(frozen=True, slots=True)
class RibbonOverlay:
    """A stretch of the ribbon to redraw in a distinct style (unpaved / ferry)."""

    kind: str  # unpaved | ferry
    points: list[tuple[float, float]]  # polyline along the ribbon for this span


@dataclass(slots=True)
class StripLayout:
    """A schematic strip ready to render."""

    path: list[tuple[float, float]]  # polyline nodes, one per segment boundary
    markers: list[PlacedMarker]
    ribbon: list[str]  # ordered road names (the road-name ribbon)
    width: float
    height: float
    overlays: list[RibbonOverlay] = field(default_factory=list)  # unpaved/ferry stretches


def _compressed_length(miles: float) -> float:
    return MIN_SEGMENT_LEN + DIST_SCALE * math.sqrt(max(miles, 0.0))


def _bend_degrees(decision: DecisionPoint | None, style: str) -> float:
    """Signed heading change (degrees, +ccw) the ribbon should bend at a turn.

    Screen/math convention (y-up): a right turn (positive ``turn_angle``,
    clockwise) decreases heading, a left turn increases it. ``style`` selects
    stylized (quantized) vs faithful (actual angle) bending.
    """
    if decision is None or not decision.turn_angle:
        return 0.0
    angle = decision.turn_angle
    if style == TURN_STYLE_FAITHFUL:
        return -max(-MAX_BEND_DEG, min(MAX_BEND_DEG, angle))
    mag = abs(angle)
    if mag >= 100.0:
        stylized = SHARP_TURN_DEG
    elif mag >= 25.0:
        stylized = NORMAL_TURN_DEG
    else:
        stylized = CONTINUE_TURN_DEG
    return -math.copysign(stylized, angle)


def _span_labels(span: RouteSpan) -> tuple[str, str]:
    """(start, end) labels for a styled span, labeled like waypoints at each end."""
    if span.kind == "ferry":
        base = span.name or "Ferry"
        return f"{base} — board", "Ferry — land"
    return "Unpaved", "Unpaved end"


def _segments_or_default(route: Route) -> list[Segment]:
    if route.segments:
        return route.segments
    return [Segment(name=route.name, start_mile=0.0, end_mile=route.length_miles)]


def _decision_at(route: Route, mile: float) -> DecisionPoint | None:
    best: DecisionPoint | None = None
    best_d = MARKER_MATCH_TOLERANCE_MILES
    for d in route.decision_points:
        delta = abs(d.mile - mile)
        if delta <= best_d:
            best, best_d = d, delta
    return best


def build_strip_layout(
    route: Route,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
    show_start: bool = True,
    show_end: bool = True,
) -> StripLayout:
    """Lay out ``route`` as a schematic strip.

    ``turn_style`` is ``"stylized"`` (default: quantized, exaggerated bends) or
    ``"faithful"`` (bend by the route's actual turn angle). ``show_start`` /
    ``show_end`` control the START/END markers -- the PDF suppresses them on
    interior pages, where the page edge is already marked by a decision.
    """
    if turn_style not in TURN_STYLES:
        raise ValueError(f"turn_style must be one of {TURN_STYLES}, got {turn_style!r}")
    segments = _segments_or_default(route)

    # 1. Build the jogging ribbon: a node per segment boundary.
    nodes: list[tuple[float, float]] = [(0.0, 0.0)]
    heading = 0.0  # radians, 0 == +x
    for i, seg in enumerate(segments):
        length = _compressed_length(seg.length_miles)
        x, y = nodes[-1]
        nodes.append((x + length * math.cos(heading), y + length * math.sin(heading)))
        if i < len(segments) - 1:  # turn at the boundary into the next segment
            heading += math.radians(_bend_degrees(_decision_at(route, seg.end_mile), turn_style))
            if turn_style == TURN_STYLE_STYLIZED:
                heading *= 1.0 - CURL_RELAX  # relax toward horizontal; curb spiral

    # 2. Map any route-mile to a point along the ribbon (linear within a segment).
    def pos_at_mile(mile: float) -> tuple[float, float]:
        for i, seg in enumerate(segments):
            if seg.start_mile <= mile <= seg.end_mile or i == len(segments) - 1:
                span = seg.end_mile - seg.start_mile
                f = 0.0 if span <= 0 else (mile - seg.start_mile) / span
                f = min(max(f, 0.0), 1.0)
                (x0, y0), (x1, y1) = nodes[i], nodes[i + 1]
                return (x0 + f * (x1 - x0), y0 + f * (y1 - y0))
        return nodes[-1]

    def cleared_pos(mile: float) -> tuple[float, float]:
        """Position at ``mile``, nudged off the START/END node if it lands on it.

        A fuel stop / waypoint right at mile 0 (or the route end) otherwise draws
        its dot and label directly over the START/END marker; push it a little way
        along the ribbon so both stay legible.
        """
        x, y = pos_at_mile(mile)
        for end_x, end_y, ax, ay in (
            (*nodes[0], *nodes[1]),  # start node, toward the next node
            (*nodes[-1], *nodes[-2]),  # end node, toward the previous node
        ):
            if math.hypot(x - end_x, y - end_y) < END_CLEAR_DIST:
                dx, dy = ax - end_x, ay - end_y
                n = math.hypot(dx, dy) or 1.0
                return end_x + dx / n * END_CLEAR_DIST, end_y + dy / n * END_CLEAR_DIST
        return x, y

    # 3. Place markers.
    # Find POIs that sit at/near the route endpoints so their name can replace
    # the generic START/END label and their duplicate marker can be suppressed.
    _start_poi = next(
        (p for p in route.pois if p.mile <= MARKER_MATCH_TOLERANCE_MILES), None
    )
    _end_poi = next(
        (p for p in reversed(route.pois) if p.mile >= route.length_miles - MARKER_MATCH_TOLERANCE_MILES),
        None,
    )
    _endpoint_poi_ids = {id(p) for p in (_start_poi, _end_poi) if p is not None}

    markers: list[PlacedMarker] = []
    if show_start:
        start_label = _start_poi.name if _start_poi else "START"
        markers.append(PlacedMarker(*nodes[0], 0.0, "start", start_label))
    for d in route.decision_points:
        x, y = pos_at_mile(d.mile)
        kind = "roundabout" if d.kind == DecisionKind.ROUNDABOUT else "decision"
        markers.append(
            PlacedMarker(
                x, y, d.mile, kind, d.instruction, d.significance, d.instruction,
                d.branches, d.roundabout_exit,
            )
        )
    for fstop in route.fuel_stops:
        x, y = cleared_pos(fstop.mile)
        markers.append(PlacedMarker(x, y, fstop.mile, "fuel", fstop.name))
    for m in route.reassurance_markers:
        x, y = cleared_pos(m.mile)
        markers.append(PlacedMarker(x, y, m.mile, "reassurance", m.label))
    for poi in route.pois:
        if id(poi) in _endpoint_poi_ids:
            continue  # already used as the start/end label
        x, y = cleared_pos(poi.mile)
        markers.append(PlacedMarker(x, y, poi.mile, poi.kind, poi.name, symbol=poi.symbol))

    # Styled spans (unpaved / ferry): a recolored ribbon stretch plus a labeled
    # marker at each end (the boarding/landing or surface-change points).
    overlays: list[RibbonOverlay] = []
    for s in route.spans:
        pts = [pos_at_mile(s.start_mile)]
        for i, seg in enumerate(segments):
            if s.start_mile < seg.end_mile < s.end_mile:
                pts.append(nodes[i + 1])
        pts.append(pos_at_mile(s.end_mile))
        overlays.append(RibbonOverlay(kind=s.kind, points=pts))
        start_label, end_label = _span_labels(s)
        sx, sy = cleared_pos(s.start_mile)
        ex, ey = cleared_pos(s.end_mile)
        markers.append(PlacedMarker(sx, sy, s.start_mile, s.kind, start_label))
        markers.append(PlacedMarker(ex, ey, s.end_mile, s.kind, end_label))

    if show_end:
        end_label = _end_poi.name if _end_poi else "END"
        markers.append(PlacedMarker(*nodes[-1], route.length_miles, "end", end_label))

    # 4. Normalize to a (0,0)-anchored box.
    xs = [p[0] for p in nodes]
    ys = [p[1] for p in nodes]
    min_x, min_y = min(xs), min(ys)
    nodes = [(x - min_x, y - min_y) for x, y in nodes]
    markers = [
        PlacedMarker(
            m.x - min_x, m.y - min_y, m.mile, m.kind, m.label, m.significance, m.instruction,
            m.branches, m.roundabout_exit, m.symbol,
        )
        for m in markers
    ]
    overlays = [
        RibbonOverlay(kind=o.kind, points=[(x - min_x, y - min_y) for x, y in o.points])
        for o in overlays
    ]
    width = max(xs) - min_x
    height = max(ys) - min_y

    return StripLayout(
        path=nodes,
        markers=markers,
        ribbon=[seg.name for seg in segments],
        width=width,
        height=height,
        overlays=overlays,
    )
