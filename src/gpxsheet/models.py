"""Core data models for the GPXSheet route graph.

These map directly onto the Route Graph Model in PRODUCT.md::

    Route
     ├─ Segments
     ├─ DecisionPoints
     ├─ ReassuranceMarkers
     ├─ FuelStops
     └─ Pages          (added in the layout/rendering milestones)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .geo import meters_to_miles


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A single route vertex."""

    lat: float
    lon: float
    ele: float | None = None


@dataclass(frozen=True, slots=True)
class Waypoint:
    """A named point of interest from the GPX (<wpt>) or OSM enrichment."""

    lat: float
    lon: float
    name: str | None = None
    symbol: str | None = None


class DecisionKind:
    """Decision-point categories from PRODUCT.md."""

    CRITICAL_TURN = "critical_turn"
    CONFIRMATION = "confirmation"
    FUEL = "fuel"
    ROUNDABOUT = "roundabout"


@dataclass(frozen=True, slots=True)
class Branch:
    """A road at a junction that the route does NOT take.

    Surfaced at a decision to disambiguate forks / multi-way intersections: the
    renderer draws a ghosted stub so the rider can tell which road to ignore.
    ``relative_angle`` is signed degrees off the route's heading (+right/-left).
    """

    direction: str  # left | right | straight | back (relative to the rider)
    relative_angle: float
    name: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    """A navigation decision along the route."""

    mile: float
    instruction: str
    significance: int
    lat: float
    lon: float
    kind: str = DecisionKind.CRITICAL_TURN
    turn_angle: float | None = None  # signed degrees; +right / -left
    branches: tuple[Branch, ...] = ()  # roads NOT taken at this junction
    roundabout_exit: int | None = None  # Nth exit, when kind == ROUNDABOUT


@dataclass(frozen=True, slots=True)
class ReassuranceMarker:
    """A confidence marker placed between decisions."""

    mile: float
    label: str
    lat: float
    lon: float
    reason: str = "interval"  # interval | town | feature | landmark


@dataclass(frozen=True, slots=True)
class FuelStop:
    """A fuel opportunity on or near the route."""

    mile: float
    name: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Segment:
    """A named stretch of road between transitions."""

    name: str
    start_mile: float
    end_mile: float

    @property
    def length_miles(self) -> float:
        return self.end_mile - self.start_mile


@dataclass(slots=True)
class FuelReport:
    """Result of fuel-gap analysis."""

    longest_gap_miles: float
    recommended: list[str] = field(default_factory=list)
    exceeds_range: bool = False
    fuel_range_miles: float | None = None


@dataclass(slots=True)
class Route:
    """The full analyzed route graph."""

    name: str
    points: list[GeoPoint]
    distances_m: list[float]  # cumulative meters, parallel to points
    waypoints: list[Waypoint] = field(default_factory=list)
    decision_points: list[DecisionPoint] = field(default_factory=list)
    reassurance_markers: list[ReassuranceMarker] = field(default_factory=list)
    fuel_stops: list[FuelStop] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    fuel_report: FuelReport | None = None
    # Hazard data from OSM enrichment; None means "not assessed" (no OSM run).
    unpaved_miles: float | None = None
    ferry_crossings: list[str] | None = None

    @property
    def length_m(self) -> float:
        return self.distances_m[-1] if self.distances_m else 0.0

    @property
    def length_miles(self) -> float:
        return meters_to_miles(self.length_m)
