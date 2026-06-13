"""Native route table built from the analyzed :class:`~gpxsheet.models.Route`.

Re-implements GPXtable's markdown/HTML route table directly on GPXsheet's
analysis graph, so the table inherits OSM enrichment (auto-discovered fuel,
road-snapped distance) and the timing layer in :mod:`gpxsheet.timing`. The column
layout matches GPXtable's exactly (``| Name | Dist. | GL | ETA | Notes``) so its
output stays a usable parity oracle; with OSM off the two should agree on the
same geometry.

Rows are the route's named waypoints (``route.pois``) plus any fuel stop
(``route.fuel_stops``, incl. OSM-discovered) that does not already coincide with
a waypoint. Each row is classified (:mod:`gpxsheet.waypoints`) for its marker /
layover / fuel-reset and timed (:mod:`gpxsheet.timing`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from .geo import MILES_PER_KM, meters_to_miles, miles_to_meters
from .models import Route
from .timing import (
    SpeedProfile,
    StopInput,
    compute_timings,
    format_sun_line,
    sun_times,
)
from .waypoints import classify

# km->miles for speed/length display (GPXtable's constant; centralized in geo).
KM_TO_MILES = MILES_PER_KM
# Default travel speed when none is given: 30 mph (GPXtable's default).
DEFAULT_SPEED_MPH = 30.0
# A fuel stop within this many miles of a named waypoint is considered the same
# stop (the waypoint row already represents it).
FUEL_NEAR_POI_MILES = 0.3

# Base column templates, identical to GPXtable's GPXTableCalculator.
_OUT_HDR = "| Name                           |   Dist. | GL |  ETA  | Notes"
_OUT_SEP = "| :----------------------------- | ------: | -- | ----: | :----"
_OUT_FMT = "| {:30.30} | {:>7} | {:>2} | {:>5} | {}{}"
# A Road column (before Notes) appears when OSM road names are available.
_OUT_HDR_ROAD = (
    "| Name                           |   Dist. | GL |  ETA  | Road                     | Notes"
)
_OUT_SEP_ROAD = (
    "| :----------------------------- | ------: | -- | ----: | :----------------------- | :----"
)
_OUT_FMT_ROAD = "| {:30.30} | {:>7} | {:>2} | {:>5} | {:24.24} | {}{}"
_LLP_HDR = "|        Lat,Lon       "
_LLP_SEP = "| :------------------: "
_LLP_FMT = "| {:-10.4f},{:.4f} "

# Geometry-only segments are named "Leg N"; those are not real road names.
_LEG_RE = re.compile(r"^Leg \d+$")


@dataclass(frozen=True, slots=True)
class _Row:
    name: str
    lat: float
    lon: float
    distance_m: float
    symbol: str | None


def _collect_rows(route: Route) -> list[_Row]:
    """Ordered table rows: named waypoints + non-duplicate fuel stops.

    Fuel stops (including OSM-discovered ones) that fall within
    :data:`FUEL_NEAR_POI_MILES` of a named waypoint are dropped -- the waypoint
    row already stands for that stop (rider waypoints win, as in enrichment).
    """
    rows: list[_Row] = [
        _Row(p.name, p.lat, p.lon, miles_to_meters(p.mile), p.symbol)
        for p in route.pois
    ]
    poi_miles = [p.mile for p in route.pois]
    for fs in route.fuel_stops:
        if any(abs(fs.mile - pm) < FUEL_NEAR_POI_MILES for pm in poi_miles):
            continue
        # Give an unlabelled OSM/GPX fuel stop a Gas Station symbol so the
        # classifier marks it 'G' and treats it as a fuel reset.
        rows.append(_Row(fs.name, fs.lat, fs.lon, miles_to_meters(fs.mile), "Gas Station"))
    rows.sort(key=lambda r: r.distance_m)
    return rows


def _fmt_speed_mph(mph: float, imperial: bool) -> str:
    return f"{mph:.2f} mph" if imperial else f"{mph / KM_TO_MILES:.2f} km/h"


def _resolve_speed_profile(
    route: Route, speed: float, imperial: bool
) -> tuple[SpeedProfile, bool, float]:
    """Pick the table's speed profile: ``(profile, variable, flat_mph)``.

    A user-supplied ``speed`` (mph imperial, kph metric) wins and forces a flat
    profile -- the explicit override of OSM speeds. Otherwise, when OSM provided a
    speed-limit profile, use it (variable ETAs); else fall back to a flat 30 mph.
    """
    if speed > 0:
        return SpeedProfile.flat(speed if imperial else speed * KM_TO_MILES), False, (
            speed if imperial else speed * KM_TO_MILES
        )
    if route.speed_samples_mph:
        return SpeedProfile.from_breakpoints_mph(route.speed_samples_mph), True, 0.0
    return SpeedProfile.flat(DEFAULT_SPEED_MPH), False, DEFAULT_SPEED_MPH


def _speed_line(
    profile: SpeedProfile, length_miles: float, variable: bool, flat_mph: float, imperial: bool
) -> str:
    """The ``* Speed`` / ``* Default speed`` header line for a section."""
    if variable:
        avg = profile.average_mph(length_miles)
        return f"* Speed: OSM limits (avg {_fmt_speed_mph(avg, imperial)})"
    return f"* Default speed: {_fmt_speed_mph(flat_mph, imperial)}"


def _fmt_length(meters: float, imperial: bool, units: bool = False) -> str:
    """Integer distance, optionally with a unit suffix (GPXtable's rounding)."""
    if imperial:
        value, suffix = round(meters_to_miles(meters)), " mi"
    else:
        value, suffix = round(meters / 1000.0), " km"
    return f"{value}{suffix if units else ''}"


def _fmt_layover(layover: timedelta) -> str:
    # str(timedelta(minutes=15)) == "0:15:00"; trim the seconds -> "0:15".
    return f" (+{str(layover)[:-3]})" if layover else ""


def _fmt_mile(mile: float, imperial: bool) -> str:
    """A one-decimal distance marker (miles imperial, km metric), no unit."""
    return f"{mile:.1f}" if imperial else f"{mile / KM_TO_MILES:.1f}"


def _layover_before(mile: float, rows: list[_Row], classes: list) -> timedelta:
    """Total layover of interior stops reached before ``mile`` (for cue ETAs)."""
    total = timedelta()
    last = len(rows) - 1
    for i, (row, cls) in enumerate(zip(rows, classes, strict=True)):
        if 0 < i < last and meters_to_miles(row.distance_m) < mile:
            total += timedelta(minutes=cls.delay)
    return total


def _cue_lines(
    decisions: list[tuple[float, str, tuple]],
    rows: list[_Row],
    classes: list,
    *,
    imperial: bool,
    departure: datetime | None,
    tz: tzinfo | None,
    profile: SpeedProfile,
) -> list[str]:
    """A ``## Turn-by-turn`` cue table from ``(mile, instruction, branches)`` tuples.

    Miles are section-local (a per-day slice passes day-relative miles, matching
    its rebased ``rows``/``profile``). Columns are ``Mile | [ETA] | Cue``; the ETA
    column appears only with a departure. The cue is the instruction plus any
    named roads not taken.
    """
    eta_on = departure is not None
    lines = ["", "## Turn-by-turn"]
    lines.append("| Mile |  ETA  | Cue" if eta_on else "| Mile | Cue")
    lines.append("| ---: | ----: | :--" if eta_on else "| ---: | :--")
    for mile_val, instruction, branches in decisions:
        cue = instruction
        skipped = [b.name for b in branches if b.name]
        if skipped:
            cue += f" — skip {', '.join(skipped)}"
        mile = _fmt_mile(mile_val, imperial)
        if eta_on:
            assert departure is not None
            arrival = (
                departure + profile.time_to(mile_val) + _layover_before(mile_val, rows, classes)
            )
            eta = arrival.astimezone(tz).strftime("%H:%M")
            lines.append(f"| {mile:>4} | {eta:>5} | {cue}")
        else:
            lines.append(f"| {mile:>4} | {cue}")
    return lines


def _road_at(route: Route, mile: float) -> str | None:
    """The OSM road name covering ``mile`` (None for a gap or a 'Leg N' segment)."""
    for seg in route.segments:
        if seg.start_mile <= mile <= seg.end_mile and not _LEG_RE.match(seg.name):
            return seg.name
    return None


def _table_lines(
    rows: list[_Row],
    classes: list,
    timings: list,
    roads: list[str | None],
    *,
    imperial: bool,
    tz: tzinfo | None,
    display_coordinates: bool,
) -> list[str]:
    """The header, separator and data rows for one table section.

    A Road column is added when any row has a road name (``roads`` not all None).
    """
    show_road = any(roads)
    out_hdr, out_sep = (
        (_OUT_HDR_ROAD, _OUT_SEP_ROAD) if show_road else (_OUT_HDR, _OUT_SEP)
    )
    if display_coordinates:
        lines = [f"{_LLP_HDR}{out_hdr}", f"{_LLP_SEP}{out_sep}"]
    else:
        lines = [out_hdr, out_sep]

    last = len(rows) - 1
    for i, (row, cls, t, road) in enumerate(
        zip(rows, classes, timings, roads, strict=True)
    ):
        is_edge = i == 0 or i == last
        if cls.fuel_reset or i == last:
            dist = f"{_fmt_length(t.since_gas_m, imperial)}/{_fmt_length(t.total_m, imperial)}"
        else:
            dist = _fmt_length(t.total_m, imperial)
        marker = "" if is_edge else cls.marker
        eta = t.arrival.astimezone(tz).strftime("%H:%M") if t.arrival else ""
        prefix = _LLP_FMT.format(row.lat, row.lon) if display_coordinates else ""
        name = (row.name or "").replace("\n", " ")
        notes, layover = cls.symbol or "", _fmt_layover(t.layover)
        if show_road:
            body = _OUT_FMT_ROAD.format(name, dist, marker, eta, road or "", notes, layover)
        else:
            body = _OUT_FMT.format(name, dist, marker, eta, notes, layover)
        lines.append(prefix + body)
    return lines


def _day_title(route: Route, day: int) -> str:
    """The ``## Day N`` heading, suffixed with the day's track name when known."""
    name = route.day_names[day] if day < len(route.day_names) else ""
    return f"## Day {day + 1}: {name}" if name else f"## Day {day + 1}"


def _day_bounds_miles(route: Route) -> list[float]:
    """Mile boundaries ``[0, break1, …, length]`` from ``route.day_breaks``."""
    breaks = [meters_to_miles(route.distances_m[i]) for i in route.day_breaks]
    return [0.0, *breaks, route.length_miles]


_DAY_EPS = 1e-6
# A stop within this of a day boundary belongs to BOTH adjacent days: an overnight
# stop is the end of one day and the start of the next.
_DAY_BOUNDARY_TOL_MILES = 0.3


def _in_day(mile: float, start_mi: float, end_mi: float, is_last: bool) -> bool:
    """Whether ``mile`` falls in day ``[start_mi, end_mi]`` (boundary-inclusive).

    Both ends carry a tolerance band so a stop sitting on a day boundary is
    counted in both adjacent days. The last day has no upper bound -- a stop's
    rounded mile can land just past ``route.length_miles`` -- so the trailing stop
    is never dropped.
    """
    lo = start_mi - _DAY_BOUNDARY_TOL_MILES - _DAY_EPS
    hi = float("inf") if is_last else end_mi + _DAY_BOUNDARY_TOL_MILES + _DAY_EPS
    return lo <= mile <= hi


def _render_section(
    *,
    title: str,
    dist_label: str,
    rows: list[_Row],
    classes: list,
    roads: list[str | None],
    decisions: list[tuple[float, str, tuple]],
    length_m: float,
    profile: SpeedProfile,
    variable: bool,
    flat_mph: float,
    imperial: bool,
    departure: datetime | None,
    tz: tzinfo | None,
    display_coordinates: bool,
    show_cue: bool,
) -> list[str]:
    """Render one section (whole route, or one day): header, table, sun, cue.

    ``rows`` distances and ``profile``/``decisions`` miles are section-local
    (rebased to 0 for a per-day slice), so this is unit-agnostic to day vs route.
    """
    timings = compute_timings(
        [
            StopInput(r.distance_m, timedelta(minutes=c.delay), c.fuel_reset)
            for r, c in zip(rows, classes, strict=True)
        ],
        departure=departure,
        speed=profile,
    )
    lines = [title]
    if departure is not None:
        lines.append(f"* Departure at {departure.astimezone(tz):%c %Z}")
    lines.append(f"* {dist_label}: {_fmt_length(length_m, imperial, True)}")
    lines.append(_speed_line(profile, meters_to_miles(length_m), variable, flat_mph, imperial))
    lines.append("")
    lines += _table_lines(
        rows, classes, timings, roads,
        imperial=imperial, tz=tz, display_coordinates=display_coordinates,
    )
    almanac = _sun_line(rows, timings, tz)
    if almanac:
        lines += ["", f"* {almanac}"]
    if show_cue and decisions:
        lines += _cue_lines(
            decisions, rows, classes,
            imperial=imperial, departure=departure, tz=tz, profile=profile,
        )
    return lines


@dataclass(frozen=True, slots=True)
class _DaySlice:
    """One section's pre-computed, section-local inputs (route or a single day).

    Shared by the markdown and JSON renderers so the day-splitting / mile-rebasing
    logic lives in exactly one place. ``rows`` distances and ``profile``/
    ``decisions`` miles are rebased to 0 for a per-day slice.
    """

    day: int  # 0-based section index
    title: str
    dist_label: str
    rows: list[_Row]
    classes: list[Any]
    roads: list[str | None]
    decisions: list[tuple[float, str, tuple]]
    length_m: float
    profile: SpeedProfile
    variable: bool
    flat_mph: float
    departure: datetime | None


def _day_slices(
    route: Route,
    *,
    imperial: bool,
    speed: float,
    departure: datetime | None,
    classifier: list[dict[str, Any]] | None,
) -> list[_DaySlice]:
    """Split ``route`` into renderable sections (whole route, or one per day).

    A single-track route yields one section (``## Route: <name>``); a multi-track
    route (``route.day_breaks``) yields one per day, each rebased to mile 0 with
    its own departure (+24h/day).
    """
    rows = _collect_rows(route)
    classes = [classify(r.name, r.symbol, classifier) for r in rows]
    roads = [_road_at(route, meters_to_miles(r.distance_m)) for r in rows]
    profile, variable, flat_mph = _resolve_speed_profile(route, speed, imperial)

    bounds = _day_bounds_miles(route)
    multiday = len(route.day_breaks) > 0

    slices: list[_DaySlice] = []
    for day, (start_mi, end_mi) in enumerate(zip(bounds, bounds[1:], strict=False)):
        is_last = day == len(bounds) - 2
        start_m = miles_to_meters(start_mi)
        sel = [
            i for i, r in enumerate(rows)
            if _in_day(meters_to_miles(r.distance_m), start_mi, end_mi, is_last)
        ]
        day_rows = [
            _Row(
                rows[i].name, rows[i].lat, rows[i].lon,
                max(0.0, rows[i].distance_m - start_m), rows[i].symbol,
            )
            for i in sel
        ]
        day_decisions = [
            (max(0.0, dp.mile - start_mi), dp.instruction, dp.branches)
            for dp in route.decision_points
            if _in_day(dp.mile, start_mi, end_mi, is_last)
        ]
        slices.append(
            _DaySlice(
                day=day,
                title=_day_title(route, day) if multiday else f"## Route: {route.name}",
                dist_label="Day distance" if multiday else "Total distance",
                rows=day_rows,
                classes=[classes[i] for i in sel],
                roads=[roads[i] for i in sel],
                decisions=day_decisions,
                length_m=miles_to_meters(end_mi - start_mi),
                profile=profile.slice(start_mi, end_mi) if multiday else profile,
                variable=variable,
                flat_mph=flat_mph,
                departure=departure + timedelta(days=day) if departure else None,
            )
        )
    return slices


def build_table_markdown(
    route: Route,
    *,
    imperial: bool = True,
    speed: float = 0.0,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    display_coordinates: bool = False,
    show_cue: bool = False,
    classifier: list[dict[str, Any]] | None = None,
) -> str:
    """Render ``route`` to GPXtable's markdown table format.

    ``speed`` of 0 uses the 30 mph default. ``departure`` enables the ETA column
    and the sunrise/sunset almanac line. ``show_cue`` appends a turn-by-turn cue
    table. A multi-track route (``route.day_breaks``) renders one section per day,
    each with its own mileage (restarting at 0), departure (+24h/day) and almanac.
    """
    slices = _day_slices(
        route, imperial=imperial, speed=speed, departure=departure, classifier=classifier
    )
    sections = [
        _render_section(
            title=s.title,
            dist_label=s.dist_label,
            rows=s.rows,
            classes=s.classes,
            roads=s.roads,
            decisions=s.decisions,
            length_m=s.length_m,
            profile=s.profile,
            variable=s.variable,
            flat_mph=s.flat_mph,
            imperial=imperial,
            departure=s.departure,
            tz=tz,
            display_coordinates=display_coordinates,
            show_cue=show_cue,
        )
        for s in slices
    ]
    # A blank line between day sections so each "## Day N" header renders.
    return "\n\n".join("\n".join(s) for s in sections) + "\n"


def _section_sun_times(rows: list[_Row], timings: list) -> dict[str, datetime] | None:
    """``sun_times`` for a section, or None without both a start and end arrival.

    Sunrise is computed at the first stop's arrival, sunset at the last stop's
    departure (arrival + its layover). Shared by the markdown almanac line and the
    JSON ``sun`` block.
    """
    if not rows or timings[0].arrival is None or timings[-1].arrival is None:
        return None
    end_layover = sum((t.layover for t in timings), timedelta())
    return sun_times(
        rows[0].lat,
        rows[0].lon,
        timings[0].arrival,
        rows[-1].lat,
        rows[-1].lon,
        timings[-1].arrival + end_layover,
    )


def _sun_line(rows: list[_Row], timings: list, tz: tzinfo | None) -> str | None:
    """The sunrise/sunset almanac line, or None without a start/end arrival."""
    times = _section_sun_times(rows, timings)
    return format_sun_line(times, tz) if times else None


# ---------------------------------------------------------------------------
# Structured JSON output
# ---------------------------------------------------------------------------
#
# The same per-day sections as the markdown table, as data instead of text.
# Conventions (see docs/web-api.md / library-api.md):
#   * Numbers are ALWAYS imperial (miles / mph), rounded to 1 decimal -- the
#     ``units`` knob only affects the md/html render, never the JSON.
#   * Datetimes are ISO 8601 carrying the display-tz offset, or ``null``.
#   * Optional values (eta/road/symbol/sun) are present as ``null`` when absent.
#   * lat/lon and the per-section cue are always included (not gated on the
#     ``coordinates``/``cue`` display flags).


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@dataclass(slots=True)
class TableRow:
    """One table row (a waypoint or fuel stop), section-local distances."""

    name: str
    mile: float  # distance from the section start
    since_gas_mi: float  # distance since the last fuel reset
    marker: str  # "" | "G" | "L" | "GL" (true classification, not edge-blanked)
    gas: bool
    lunch: bool
    fuel_reset: bool
    layover_min: int
    eta: datetime | None
    road: str | None  # OSM road name covering this mile, else null
    symbol: str | None  # effective GPX/classifier symbol (the Notes column)
    lat: float
    lon: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mile": self.mile,
            "since_gas_mi": self.since_gas_mi,
            "marker": self.marker,
            "gas": self.gas,
            "lunch": self.lunch,
            "fuel_reset": self.fuel_reset,
            "layover_min": self.layover_min,
            "eta": _iso(self.eta),
            "road": self.road,
            "symbol": self.symbol,
            "lat": self.lat,
            "lon": self.lon,
        }


@dataclass(slots=True)
class CueEntry:
    """One turn-by-turn cue (from a decision point), section-local mile."""

    mile: float
    eta: datetime | None
    instruction: str
    skip: list[str]  # named roads not taken at this junction

    def to_dict(self) -> dict[str, Any]:
        return {
            "mile": self.mile,
            "eta": _iso(self.eta),
            "instruction": self.instruction,
            "skip": self.skip,
        }


@dataclass(slots=True)
class TableSpeed:
    """The section's speed model: ``osm`` (variable limits) or ``flat``."""

    mode: str  # "osm" | "flat"
    avg_mph: float  # realized average over the section either way

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "avg_mph": self.avg_mph}


@dataclass(slots=True)
class TableSun:
    """Sunrise at the section start, sunset at its end (display tz)."""

    sunrise: datetime | None
    sunset: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {"sunrise": _iso(self.sunrise), "sunset": _iso(self.sunset)}


@dataclass(slots=True)
class TableSection:
    """One section: the whole route, or one day of a multi-track route."""

    day: int  # 1-based
    title: str  # e.g. "Route: Foo" or "Day 1: Coast" ("## " stripped)
    departure: datetime | None
    distance_mi: float
    speed: TableSpeed
    sun: TableSun | None
    rows: list[TableRow]
    cue: list[CueEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "title": self.title,
            "departure": _iso(self.departure),
            "distance_mi": self.distance_mi,
            "speed": self.speed.to_dict(),
            "sun": self.sun.to_dict() if self.sun else None,
            "rows": [r.to_dict() for r in self.rows],
            "cue": [c.to_dict() for c in self.cue],
        }


@dataclass(slots=True)
class TableDocument:
    """The full structured route table: route metadata + per-day sections."""

    name: str
    units: str  # always "imperial" (the JSON numbers' unit)
    sections: list[TableSection]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "units": self.units,
            "sections": [s.to_dict() for s in self.sections],
        }


def _section_eta(
    mile: float,
    slc: _DaySlice,
    tz: tzinfo | None,
) -> datetime | None:
    """ETA at section-local ``mile`` (departure + travel + prior layovers)."""
    if slc.departure is None:
        return None
    arrival = slc.departure + slc.profile.time_to(mile) + _layover_before(
        mile, slc.rows, slc.classes
    )
    return arrival.astimezone(tz) if tz else arrival


def build_table_data(
    route: Route,
    *,
    speed: float = 0.0,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    classifier: list[dict[str, Any]] | None = None,
) -> TableDocument:
    """Build the structured (imperial) route table from an analyzed ``route``.

    The data counterpart of :func:`build_table_markdown` -- same sections, rows
    and timings, as a typed :class:`TableDocument`. ``speed`` is interpreted as
    mph (JSON is imperial-only); ``departure`` populates ETAs, the cue ETAs and
    the sun block. Multi-track routes yield one section per day (rebased to mile
    0, +24h/day).
    """
    slices = _day_slices(
        route, imperial=True, speed=speed, departure=departure, classifier=classifier
    )
    sections: list[TableSection] = []
    for slc in slices:
        timings = compute_timings(
            [
                StopInput(r.distance_m, timedelta(minutes=c.delay), c.fuel_reset)
                for r, c in zip(slc.rows, slc.classes, strict=True)
            ],
            departure=slc.departure,
            speed=slc.profile,
        )
        rows = [
            TableRow(
                name=(r.name or "").replace("\n", " "),
                mile=round(meters_to_miles(r.distance_m), 1),
                since_gas_mi=round(meters_to_miles(t.since_gas_m), 1),
                marker=c.marker,
                gas="G" in c.marker,
                lunch="L" in c.marker,
                fuel_reset=c.fuel_reset,
                layover_min=round(t.layover.total_seconds() / 60),
                eta=t.arrival.astimezone(tz) if (t.arrival and tz) else t.arrival,
                road=road,
                symbol=c.symbol or None,
                lat=round(r.lat, 5),
                lon=round(r.lon, 5),
            )
            for r, c, t, road in zip(slc.rows, slc.classes, timings, slc.roads, strict=True)
        ]
        length_mi = meters_to_miles(slc.length_m)
        if slc.variable:
            speed_obj = TableSpeed("osm", round(slc.profile.average_mph(length_mi), 1))
        else:
            speed_obj = TableSpeed("flat", round(slc.flat_mph, 1))
        st = _section_sun_times(slc.rows, timings)
        sun = (
            TableSun(
                sunrise=st["Sunrise"].astimezone(tz) if tz else st["Sunrise"],
                sunset=st["Sunset"].astimezone(tz) if tz else st["Sunset"],
            )
            if st
            else None
        )
        cue = [
            CueEntry(
                mile=round(mile_val, 1),
                eta=_section_eta(mile_val, slc, tz),
                instruction=instruction,
                skip=[b.name for b in branches if b.name],
            )
            for mile_val, instruction, branches in slc.decisions
        ]
        dep = slc.departure.astimezone(tz) if (slc.departure and tz) else slc.departure
        sections.append(
            TableSection(
                day=slc.day + 1,
                title=slc.title.removeprefix("## "),
                departure=dep,
                distance_mi=round(length_mi, 1),
                speed=speed_obj,
                sun=sun,
                rows=rows,
                cue=cue,
            )
        )
    return TableDocument(name=route.name, units="imperial", sections=sections)


def build_table_json(
    route: Route,
    *,
    speed: float = 0.0,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    classifier: list[dict[str, Any]] | None = None,
) -> str:
    """The structured route table as a JSON string (see :func:`build_table_data`)."""
    doc = build_table_data(
        route, speed=speed, departure=departure, tz=tz, classifier=classifier
    )
    return json.dumps(doc.to_dict())


def markdown_to_html(md: str) -> str:
    """Convert table markdown to HTML, with a ``gpxtable`` CSS class on the table
    (the SPA styles ``.gpxtable``) and raw HTML escaped."""
    import markdown2

    return markdown2.markdown(
        md,
        extras={"tables": None, "html-classes": {"table": "gpxtable"}},
        safe_mode="escape",
    )


def parse_departure(
    departure: str | None, timezone: str | None
) -> tuple[datetime | None, tzinfo | None]:
    """Turn the API/CLI ``departure`` + ``timezone`` strings into ``(depart_at, tz)``.

    Both are optional. ``departure`` accepts natural language ("9:00 AM",
    "July 4 2pm") or ISO, defaulting unspecified fields to today at the top of the
    hour. Raises ``ValueError`` on an unparseable date or unknown timezone.
    """
    import dateutil.parser
    import dateutil.tz

    tz: tzinfo | None = None
    if timezone:
        tz = dateutil.tz.gettz(timezone)
        if tz is None:
            raise ValueError(f"unknown timezone {timezone!r}")

    depart_at: datetime | None = None
    if departure:
        default = datetime.now(tz or dateutil.tz.tzlocal()).replace(
            minute=0, second=0, microsecond=0
        )
        try:
            depart_at = dateutil.parser.parse(departure, default=default)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"invalid departure time {departure!r}: {exc}") from exc
    return depart_at, tz


# Output formats the native renderer accepts, and their file extensions.
TABLE_FORMATS = ("html", "markdown", "json")
EXTENSIONS = {"html": "html", "markdown": "md", "json": "json"}


def render_table(
    gpx_source: str | Path,
    output_path: str | Path,
    *,
    fmt: str = "html",
    imperial: bool = True,
    speed: float = 0.0,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    display_coordinates: bool = False,
    show_cue: bool = False,
    osm: bool = True,
) -> Path:
    """Analyze ``gpx_source`` and write its native route table to ``output_path``.

    Runs the full analysis (OSM on by default, ``osm=False`` for a fast offline
    table) under the default sport-touring profile so waypoints and fuel are
    populated, then renders ``html``, ``markdown`` or ``json``. The ``json``
    output is always imperial (``imperial``/``display_coordinates``/``show_cue``
    do not apply -- lat/lon and the cue are always present).
    """
    if fmt not in TABLE_FORMATS:
        raise ValueError(f"fmt must be one of {TABLE_FORMATS}, got {fmt!r}")
    from . import analyze

    route = analyze(str(gpx_source), osm=osm)
    if fmt == "json":
        text = build_table_json(route, speed=speed, departure=departure, tz=tz)
    else:
        md = build_table_markdown(
            route,
            imperial=imperial,
            speed=speed,
            departure=departure,
            tz=tz,
            display_coordinates=display_coordinates,
            show_cue=show_cue,
        )
        text = markdown_to_html(md) if fmt == "html" else md
    out = Path(output_path)
    out.write_text(text, encoding="utf-8")
    return out
