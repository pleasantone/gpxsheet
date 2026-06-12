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

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from .geo import meters_to_miles, miles_to_meters
from .models import Route
from .timing import (
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

# Column templates, identical to GPXtable's GPXTableCalculator.
_OUT_HDR = "| Name                           |   Dist. | GL |  ETA  | Notes"
_OUT_SEP = "| :----------------------------- | ------: | -- | ----: | :----"
_OUT_FMT = "| {:30.30} | {:>7} | {:>2} | {:>5} | {}{}"
_LLP_HDR = "|        Lat,Lon       "
_LLP_SEP = "| :------------------: "
_LLP_FMT = "| {:-10.4f},{:.4f} "


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


def _resolve_speed_kph(speed: float, imperial: bool) -> float:
    """Travel speed in km/h: ``speed`` (mph if imperial) or the 30 mph default."""
    if speed <= 0:
        return DEFAULT_SPEED_MPH / KM_TO_MILES
    return speed / KM_TO_MILES if imperial else speed


def _fmt_length(meters: float, imperial: bool, units: bool = False) -> str:
    """Integer distance, optionally with a unit suffix (GPXtable's rounding)."""
    if imperial:
        value, suffix = round(meters_to_miles(meters)), " mi"
    else:
        value, suffix = round(meters / 1000.0), " km"
    return f"{value}{suffix if units else ''}"


def _fmt_speed(speed_kph: float, imperial: bool) -> str:
    return (
        f"{speed_kph * KM_TO_MILES:.2f} mph" if imperial else f"{speed_kph:.2f} km/h"
    )


def _fmt_layover(layover: timedelta) -> str:
    # str(timedelta(minutes=15)) == "0:15:00"; trim the seconds -> "0:15".
    return f" (+{str(layover)[:-3]})" if layover else ""


def build_table_markdown(
    route: Route,
    *,
    imperial: bool = True,
    speed: float = 0.0,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    display_coordinates: bool = False,
    classifier: list[dict[str, Any]] | None = None,
) -> str:
    """Render ``route`` to GPXtable's markdown table format.

    ``speed`` of 0 uses the 30 mph default. ``departure`` enables the ETA column
    and the sunrise/sunset almanac line.
    """
    rows = _collect_rows(route)
    speed_kph = _resolve_speed_kph(speed, imperial)
    classes = [classify(r.name, r.symbol, classifier) for r in rows]
    timings = compute_timings(
        [
            StopInput(r.distance_m, timedelta(minutes=c.delay), c.fuel_reset)
            for r, c in zip(rows, classes, strict=True)
        ],
        departure=departure,
        speed_kph=speed_kph,
    )

    lines: list[str] = [f"## Route: {route.name}"]
    if departure is not None:
        lines.append(f"* Departure at {departure.astimezone(tz):%c %Z}")
    lines.append(f"* Total distance: {_fmt_length(route.length_m, imperial, True)}")
    lines.append(f"* Default speed: {_fmt_speed(speed_kph, imperial)}")
    lines.append("")
    if display_coordinates:
        lines.append(f"{_LLP_HDR}{_OUT_HDR}")
        lines.append(f"{_LLP_SEP}{_OUT_SEP}")
    else:
        lines.append(_OUT_HDR)
        lines.append(_OUT_SEP)

    last = len(rows) - 1
    for i, (row, cls, t) in enumerate(zip(rows, classes, timings, strict=True)):
        is_edge = i == 0 or i == last
        if cls.fuel_reset or i == last:
            dist = (
                f"{_fmt_length(t.since_gas_m, imperial)}/{_fmt_length(t.total_m, imperial)}"
            )
        else:
            dist = _fmt_length(t.total_m, imperial)
        marker = "" if is_edge else cls.marker
        eta = t.arrival.astimezone(tz).strftime("%H:%M") if t.arrival else ""
        prefix = _LLP_FMT.format(row.lat, row.lon) if display_coordinates else ""
        lines.append(
            prefix
            + _OUT_FMT.format(
                (row.name or "").replace("\n", " "),
                dist,
                marker,
                eta,
                cls.symbol or "",
                _fmt_layover(t.layover),
            )
        )

    almanac = _sun_line(route, rows, timings, tz)
    if almanac:
        lines += ["", f"* {almanac}"]
    return "\n".join(lines) + "\n"


def _sun_line(
    route: Route, rows: list[_Row], timings: list, tz: tzinfo | None
) -> str | None:
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
    """Convert table markdown to HTML (delegates to the shared GPXtable styling)."""
    from .table import markdown_to_html as _to_html

    return _to_html(md)


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
    depart_at: datetime | None = None,
    tz: tzinfo | None = None,
    display_coordinates: bool = False,
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
        departure=depart_at,
        tz=tz,
        display_coordinates=display_coordinates,
    )
    text = markdown_to_html(md) if fmt == "html" else md
    out = Path(output_path)
    out.write_text(text, encoding="utf-8")
    return out
