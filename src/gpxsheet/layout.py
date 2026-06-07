"""Schematic Layout Engine (Milestone 2).

Turns the analyzed :class:`~gpxsheet.models.Route` graph into a *schematic* strip
-- not a plot of the GPX. Following PRODUCT.md's "Hybrid Schematic Map System":

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
from dataclasses import dataclass

from .models import DecisionPoint, Route, Segment

# Schematic sizing (arbitrary units; the renderer scales to fit). A larger floor
# plus a gentler distance term makes segment lengths more uniform -- short
# segments get enough room for their labels, long roads stay compressed
# (information density matters more than raw distance, per PRODUCT.md).
MIN_SEGMENT_LEN = 2.6  # every segment gets at least this much strip, however short
DIST_SCALE = 1.0  # multiplies sqrt(miles); sub-linear compression of long roads

# Two ways to bend the ribbon at a turn:
#   "stylized" (default): quantize to a few exaggerated angles by sharpness, so
#       the strip reads like a transit map (PRODUCT.md: "exaggerates important
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
MARKER_MATCH_TOLERANCE_MILES = 0.15


@dataclass(frozen=True, slots=True)
class PlacedMarker:
    """A marker positioned in schematic strip coordinates."""

    x: float
    y: float
    mile: float
    kind: str  # start | end | decision | fuel | reassurance
    label: str
    significance: int = 0
    instruction: str | None = None


@dataclass(slots=True)
class StripLayout:
    """A schematic strip ready to render."""

    path: list[tuple[float, float]]  # polyline nodes, one per segment boundary
    markers: list[PlacedMarker]
    ribbon: list[str]  # ordered road names (the road-name ribbon)
    width: float
    height: float


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


def build_strip_layout(route: Route, *, turn_style: str = TURN_STYLE_STYLIZED) -> StripLayout:
    """Lay out ``route`` as a schematic strip.

    ``turn_style`` is ``"stylized"`` (default: quantized, exaggerated bends) or
    ``"faithful"`` (bend by the route's actual turn angle).
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

    # 3. Place markers.
    markers: list[PlacedMarker] = []
    markers.append(PlacedMarker(*nodes[0], 0.0, "start", "START"))
    for d in route.decision_points:
        x, y = pos_at_mile(d.mile)
        markers.append(
            PlacedMarker(x, y, d.mile, "decision", d.instruction, d.significance, d.instruction)
        )
    for fstop in route.fuel_stops:
        x, y = pos_at_mile(fstop.mile)
        markers.append(PlacedMarker(x, y, fstop.mile, "fuel", fstop.name))
    for m in route.reassurance_markers:
        x, y = pos_at_mile(m.mile)
        markers.append(PlacedMarker(x, y, m.mile, "reassurance", m.label))
    markers.append(PlacedMarker(*nodes[-1], route.length_miles, "end", "END"))

    # 4. Normalize to a (0,0)-anchored box.
    xs = [p[0] for p in nodes]
    ys = [p[1] for p in nodes]
    min_x, min_y = min(xs), min(ys)
    nodes = [(x - min_x, y - min_y) for x, y in nodes]
    markers = [
        PlacedMarker(
            m.x - min_x, m.y - min_y, m.mile, m.kind, m.label, m.significance, m.instruction
        )
        for m in markers
    ]
    width = max(xs) - min_x
    height = max(ys) - min_y

    return StripLayout(
        path=nodes,
        markers=markers,
        ribbon=[seg.name for seg in segments],
        width=width,
        height=height,
    )
