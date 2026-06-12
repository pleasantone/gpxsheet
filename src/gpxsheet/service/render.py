"""The engine wrapper used by jobs: GPX bytes + params -> (artifact bytes, type).

Every operation funnels through :func:`run_job` (dispatched by an internal ``op``
string set by the endpoint), returning the bytes plus the HTTP content type and
file extension to store/serve them with.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from pydantic import BaseModel

from .models import RenderParams, ReportParams, TableParams

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "json": "application/json",
    "html": "text/html",
    "markdown": "text/markdown",
}

# A 4-tuple: (artifact bytes, HTTP content type, storage extension, download name).
JobResult = tuple[bytes, str, str, str]


def run_job(op: str, gpx_bytes: bytes, params: BaseModel) -> JobResult:
    """Run an operation and return ``(data, content_type, extension, download_name)``.

    ``op`` is ``"render"`` (PDF/PNG map; ``params`` is a :class:`RenderParams`),
    ``"table"`` (HTML/markdown route table; ``params`` is a :class:`TableParams`),
    or ``"analyze"`` / ``"validate"`` (JSON report; ``params`` is a
    :class:`ReportParams`).
    """
    if op == "analyze":
        assert isinstance(params, ReportParams)
        payload, name = _analyze_dict(gpx_bytes, params)
        return _json_result(payload, name)
    if op == "validate":
        assert isinstance(params, ReportParams)
        payload, name = _validate_dict(gpx_bytes, params)
        return _json_result(payload, name)
    if op == "render":
        assert isinstance(params, RenderParams)
        return _render_result(gpx_bytes, params)
    if op == "table":
        assert isinstance(params, TableParams)
        return _table_result(gpx_bytes, params)
    raise ValueError(f"unknown job op {op!r}")


def _safe_filename(name: str | None, ext: str) -> str:
    """An ASCII, header-safe download filename derived from the route name."""
    base = re.sub(r"[^A-Za-z0-9._ -]", "", (name or "route")).strip() or "route"
    return f"{base[:80]}.{ext}"


def _json_result(payload: dict, name: str | None) -> JobResult:
    return (
        json.dumps(payload).encode(),
        _CONTENT_TYPES["json"],
        "json",
        _safe_filename(name, "json"),
    )


def _render_result(gpx_bytes: bytes, params: RenderParams) -> JobResult:
    from gpxsheet.analysis import derive_products
    from gpxsheet.pdf import render_layout

    from .analysis_cache import get_core

    core = get_core(gpx_bytes, osm=True)
    route = derive_products(core, profile=params.profile, fuel_range=params.fuel_range)
    ext = params.format  # "pdf" | "png"
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / f"out.{ext}"
        render_layout(
            route,
            out_path,
            layout=params.layout,
            fmt=params.format,
            turn_style=params.turn_style,
            paper=params.paper,
            lanes_per_page=params.lanes_per_page,
            decisions_per_lane=params.decisions_per_lane,
            show_branches=params.show_branches,
        )
        return out_path.read_bytes(), _CONTENT_TYPES[ext], ext, _safe_filename(route.name, ext)


def _table_result(gpx_bytes: bytes, params: TableParams) -> JobResult:
    """A native route table (analysis graph) as HTML or markdown.

    Runs the analysis (OSM on by default; ``--no-osm`` for a fast offline table)
    so the table inherits auto-discovered fuel and road-snapped distance.
    """
    from gpxsheet.analysis import derive_products
    from gpxsheet.routetable import (
        build_table_markdown,
        markdown_to_html,
        parse_departure,
    )

    from .analysis_cache import get_core

    depart_at, tz = parse_departure(params.departure, params.timezone)
    route = derive_products(get_core(gpx_bytes, osm=params.osm))
    md = build_table_markdown(
        route,
        imperial=(params.units == "imperial"),
        speed=params.speed,
        departure=depart_at,
        tz=tz,
        display_coordinates=params.coordinates,
        show_cue=params.cue,
    )
    if params.format == "html":
        data, ext = markdown_to_html(md).encode(), "html"
    else:
        data, ext = md.encode(), "md"
    content_type = _CONTENT_TYPES["html" if params.format == "html" else "markdown"]
    return data, content_type, ext, _safe_filename(route.name, ext)


def _analyzed_route(gpx_bytes: bytes, params: ReportParams, *, include_hazards: bool = False):
    from gpxsheet.analysis import derive_products

    from .analysis_cache import get_core

    return derive_products(
        get_core(gpx_bytes, osm=True),
        profile=params.profile,
        fuel_range=params.fuel_range,
        include_hazards=include_hazards,
    )


def _analyze_dict(gpx_bytes: bytes, params: ReportParams) -> tuple[dict, str | None]:
    """The structured analysis summary (for ``/v1/analyze``)."""
    route = _analyzed_route(gpx_bytes, params)
    payload = {
        "name": route.name,
        "length_miles": round(route.length_miles, 1),
        "decision_points": [
            {"mile": d.mile, "instruction": d.instruction, "significance": d.significance}
            for d in route.decision_points
        ],
        "fuel_stops": [{"mile": f.mile, "name": f.name} for f in route.fuel_stops],
        "segments": [
            {"name": s.name, "start_mile": s.start_mile, "end_mile": s.end_mile}
            for s in route.segments
        ],
        "longest_fuel_gap_miles": (
            route.fuel_report.longest_gap_miles if route.fuel_report else None
        ),
    }
    return payload, route.name


def _validate_dict(gpx_bytes: bytes, params: ReportParams) -> tuple[dict, str | None]:
    """Validation findings (for ``/v1/validate``); warnings don't fail the job."""
    from gpxsheet.validate import validate_route

    route = _analyzed_route(gpx_bytes, params, include_hazards=True)
    findings = validate_route(route, fuel_range=params.fuel_range)
    payload = {
        "name": route.name,
        "length_miles": round(route.length_miles, 1),
        "findings": [
            {"level": f.level, "code": f.code, "message": f.message} for f in findings
        ],
    }
    return payload, route.name
