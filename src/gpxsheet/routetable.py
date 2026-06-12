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

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from .geo import meters_to_miles, miles_to_meters
from .models import Route
from .timing import (
    SpeedProfile,
    StopInput,
    compute_timings,
    format_sun_line,
    sun_times,
)
from .waypoints import classify

# Miles->km for speed/length display, matching GPXtable's constant exactly.
KM_TO_MILES = 0.621371
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
    rows = _collect_rows(route)
    classes = [classify(r.name, r.symbol, classifier) for r in rows]
    roads = [_road_at(route, meters_to_miles(r.distance_m)) for r in rows]
    profile, variable, flat_mph = _resolve_speed_profile(route, speed, imperial)

    bounds = _day_bounds_miles(route)
    multiday = len(route.day_breaks) > 0

    sections: list[list[str]] = []
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
        sections.append(
            _render_section(
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
                imperial=imperial,
                departure=departure + timedelta(days=day) if departure else None,
                tz=tz,
                display_coordinates=display_coordinates,
                show_cue=show_cue,
            )
        )

    # A blank line between day sections so each "## Day N" header renders.
    return "\n\n".join("\n".join(s) for s in sections) + "\n"


def _sun_line(rows: list[_Row], timings: list, tz: tzinfo | None) -> str | None:
    """The sunrise/sunset almanac line, or None without a start/end arrival."""
    if not rows or timings[0].arrival is None or timings[-1].arrival is None:
        return None
    end_layover = sum((t.layover for t in timings), timedelta())
    times = sun_times(
        rows[0].lat,
        rows[0].lon,
        timings[0].arrival,
        rows[-1].lat,
        rows[-1].lon,
        timings[-1].arrival + end_layover,
    )
    return format_sun_line(times, tz) if times else None


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
TABLE_FORMATS = ("html", "markdown")
EXTENSIONS = {"html": "html", "markdown": "md"}


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
    populated, then renders ``html`` or ``markdown``.
    """
    if fmt not in TABLE_FORMATS:
        raise ValueError(f"fmt must be one of {TABLE_FORMATS}, got {fmt!r}")
    from . import analyze

    route = analyze(str(gpx_source), osm=osm)
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
