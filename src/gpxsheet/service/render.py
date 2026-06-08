"""The engine wrapper used by render jobs: GPX bytes + params -> PDF bytes."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .models import GenerateParams


def render_pdf_bytes(gpx_bytes: bytes, params: GenerateParams) -> bytes:
    """Render a route PDF in a temp dir and return its bytes.

    Thin wrapper around :func:`gpxsheet.generate_pdf` so the worker stays a pure
    function of (GPX, params) with no filesystem assumptions for the caller.
    """
    from gpxsheet import generate_pdf

    with tempfile.TemporaryDirectory() as tmp:
        gpx_path = Path(tmp) / "route.gpx"
        out_path = Path(tmp) / "route.pdf"
        gpx_path.write_bytes(gpx_bytes)
        generate_pdf(
            str(gpx_path),
            str(out_path),
            profile=params.profile,
            fuel_range=params.fuel_range,
            use_osm=params.use_osm,
            turn_style=params.turn_style,
            orientation=params.orientation,
            paper=params.paper,
            lanes_per_page=params.lanes_per_page,
            decisions_per_lane=params.decisions_per_lane,
        )
        return out_path.read_bytes()


def analyze_to_dict(gpx_bytes: bytes, params: GenerateParams) -> dict:
    """Run the analysis and return a JSON-serializable summary (for /v1/analyze)."""
    from gpxsheet import analyze

    with tempfile.TemporaryDirectory() as tmp:
        gpx_path = Path(tmp) / "route.gpx"
        gpx_path.write_bytes(gpx_bytes)
        route = analyze(
            str(gpx_path),
            profile=params.profile,
            fuel_range=params.fuel_range,
            use_osm=params.use_osm,
        )
    return {
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
