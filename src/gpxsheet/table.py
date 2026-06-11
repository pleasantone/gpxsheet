"""Route-table output: a thin wrapper over the GPXtable library that renders a
GPX as a markdown or HTML table (waypoints, cumulative distance, fuel/lunch
markers, ETAs, sunrise/sunset).

Unlike the sheet renderers, this path is **independent of GPXSheet's analyze/OSM
pipeline**: GPXtable consumes a parsed ``gpxpy`` document directly and applies its
own waypoint classifier, so table output is fast and fully offline.

Imports of ``gpxtable``/``markdown2`` are kept inside the functions (the same lazy
pattern used by ``pdf.py``/``strip.py``) so they stay off the import path for
callers that never render a table.
"""

from __future__ import annotations

import io
from datetime import datetime, tzinfo
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpxpy.gpx import GPX

TABLE_FORMATS = ("html", "markdown")

# Map a format to the file extension we store/serve it under.
EXTENSIONS = {"html": "html", "markdown": "md"}


def parse_departure(
    departure: str | None, timezone: str | None
) -> tuple[datetime | None, tzinfo | None]:
    """Turn the API/CLI ``departure`` + ``timezone`` strings into ``(depart_at, tz)``.

    Both inputs are optional. ``departure`` accepts natural language ("9:00 AM",
    "July 4 2pm") or ISO; the parse mirrors GPXtable's own CLI (dateutil with
    today-at-top-of-hour as the default for unspecified fields). Raises
    ``ValueError`` on an unparseable date or an unknown timezone.
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


def parse_gpx(gpx_source: str | Path | bytes) -> GPX:
    """Parse a GPX filesystem path (``str``/``Path``) or raw ``bytes`` content into
    a ``gpxpy`` document. Raises ``ValueError`` on malformed GPX/XML."""
    import gpxpy
    from gpxpy.gpx import GPXException

    if isinstance(gpx_source, bytes):
        text = gpx_source.decode("utf-8", errors="replace")
    else:
        text = Path(gpx_source).read_text(encoding="utf-8")
    try:
        return gpxpy.parse(text)
    except GPXException as exc:
        raise ValueError(f"could not parse GPX: {exc}") from exc


def route_title(gpx: GPX) -> str | None:
    """A human name for the document: the GPX name, else the first track/route name."""
    if gpx.name:
        return gpx.name
    for trk in gpx.tracks:
        if trk.name:
            return trk.name
    for rte in gpx.routes:
        if rte.name:
            return rte.name
    return None


def build_table_markdown(
    gpx: GPX,
    *,
    imperial: bool = True,
    speed: float = 0.0,
    depart_at: datetime | None = None,
    ignore_times: bool = False,
    display_coordinates: bool = False,
    tz: tzinfo | None = None,
) -> str:
    """Render ``gpx`` to GPXtable's markdown table. ``speed`` of 0 means auto-detect
    (GPXtable falls back to its default travel speed)."""
    from gpxtable import GPXTableCalculator

    buf = io.StringIO()
    GPXTableCalculator(
        gpx,
        output=buf,
        imperial=imperial,
        speed=speed,
        depart_at=depart_at,
        ignore_times=ignore_times,
        display_coordinates=display_coordinates,
        tz=tz,
    ).print_all()
    return buf.getvalue()


def markdown_to_html(md: str) -> str:
    """Convert GPXtable markdown to HTML, exactly as GPXtable's own CLI does
    (``tables`` extra, a ``gpxtable`` class on the table, raw HTML escaped)."""
    import markdown2

    return markdown2.markdown(
        md,
        extras={"tables": None, "html-classes": {"table": "gpxtable"}},
        safe_mode="escape",
    )


def render_table(
    gpx_source: str | Path | bytes,
    output_path: str | Path,
    *,
    fmt: str = "html",
    imperial: bool = True,
    speed: float = 0.0,
    depart_at: datetime | None = None,
    ignore_times: bool = False,
    display_coordinates: bool = False,
    tz: tzinfo | None = None,
) -> Path:
    """Render ``gpx_source`` to ``output_path`` as ``html`` or ``markdown``."""
    if fmt not in TABLE_FORMATS:
        raise ValueError(f"fmt must be one of {TABLE_FORMATS}, got {fmt!r}")
    gpx = parse_gpx(gpx_source)
    md = build_table_markdown(
        gpx,
        imperial=imperial,
        speed=speed,
        depart_at=depart_at,
        ignore_times=ignore_times,
        display_coordinates=display_coordinates,
        tz=tz,
    )
    text = markdown_to_html(md) if fmt == "html" else md
    out = Path(output_path)
    out.write_text(text, encoding="utf-8")
    return out
