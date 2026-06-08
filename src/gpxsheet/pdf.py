"""PDF generation (Milestone 3).

Composes the tank-bag document: one landscape US-Letter page per route-aware
page (see :mod:`gpxsheet.paginate`), each with a header, the schematic map strip
(Map Zone), a large-text cue zone (NEXT / AFTER / FUEL / TOTAL), and a progress
indicator. Built with matplotlib (vector PDF via ``PdfPages``), reusing
:func:`gpxsheet.strip.draw_strip` for the map.
"""

from __future__ import annotations

from pathlib import Path

from .layout import TURN_STYLE_STYLIZED, build_strip_layout
from .models import DecisionPoint, FuelStop, Route
from .paginate import paginate, slice_route
from .strip import draw_strip

_RED = "#d6312b"
_BLUE = "#2166ac"
_GREY = "#666666"


def render_pdf(
    route: Route,
    output_path: str | Path,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
) -> Path:
    """Render an already-analyzed ``route`` to a multi-page PDF."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    output_path = Path(output_path)
    pages = paginate(route)
    total = route.length_miles

    with PdfPages(output_path) as pdf:
        for i, (start, end) in enumerate(pages, start=1):
            fig = plt.figure(figsize=(11, 8.5))  # landscape US Letter
            _compose_page(fig, route, start, end, i, len(pages), total, turn_style)
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    return output_path


def _compose_page(fig, route, start, end, page_no, page_count, total, turn_style) -> None:
    """Lay out a single page (header, map strip, cue zone, progress) into ``fig``."""
    page = slice_route(route, start, end)
    layout = build_strip_layout(
        page,
        turn_style=turn_style,
        show_start=(page_no == 1),  # interior page edges are marked by a decision
        show_end=(page_no == page_count),
    )

    _draw_header(fig, route.name, page_no, page_count)
    _draw_progress(fig, start, end, total)

    # Map zone: a framed panel filling ~70% of page height; the strip is sized to
    # its own aspect (matching draw_strip's padding) and centered within it, so a
    # flat strip reads as a deliberate map area rather than empty page.
    from matplotlib.patches import Rectangle

    band = (0.03, 0.30, 0.94, 0.56)  # left, bottom, width, height (fig fraction)
    fig.patches.append(
        Rectangle(
            (band[0], band[1]), band[2], band[3], transform=fig.transFigure,
            facecolor="#fafafa", edgecolor="#dddddd", linewidth=1.0, zorder=-10,
        )
    )
    span_x = 1.24 * (layout.width or 1.0)
    span_y = 1.6 * (layout.height or 0.0) + 2.0
    aspect = span_x / span_y
    map_h = min(band[3] * 0.96, max(0.22, (band[2] * 11.0 / aspect) / 8.5))
    map_y = band[1] + (band[3] - map_h) / 2  # vertically centered in the panel
    map_ax = fig.add_axes([band[0] + 0.005, map_y, band[2] - 0.01, map_h])
    # The road-name ribbon is drawn by the page (not the strip) at a fixed spot
    # just above the panel's bottom edge, so it sits consistently across pages
    # regardless of where the strip floats inside the panel.
    draw_strip(fig, map_ax, layout, draw_ribbon=False)
    ribbon = "  ›  ".join(layout.ribbon)
    if ribbon:
        fig.text(
            0.5, band[1] + 0.018, ribbon, ha="center", va="bottom",
            fontsize=8, color="#444444",
        )
    _draw_cue_zone(fig, route, start, total)


def _draw_header(fig, name: str, page_no: int, page_count: int) -> None:
    # Truncate long route names (GPX often auto-names "<start> to <end>") so the
    # title never runs into the page counter.
    display = name if len(name) <= 60 else name[:59].rstrip() + "…"
    fig.text(0.03, 0.955, display, ha="left", va="center", fontsize=13, fontweight="bold")
    fig.text(
        0.97, 0.955, f"Page {page_no} of {page_count}",
        ha="right", va="center", fontsize=11, color=_GREY,
    )


def _draw_progress(fig, start: float, end: float, total: float) -> None:
    ax = fig.add_axes([0.06, 0.90, 0.88, 0.02])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(-1, 1)
    frac0 = start / total if total else 0.0
    frac1 = end / total if total else 1.0
    ax.plot([0, 1], [0, 0], color="#cccccc", lw=3, solid_capstyle="round")
    ax.plot([frac0, frac1], [0, 0], color=_RED, lw=6, solid_capstyle="round")  # this page
    ax.plot([frac0], [0], marker="o", color=_RED, markersize=8)
    ax.text(0, 0.9, "START", ha="left", va="bottom", fontsize=7, color=_GREY)
    ax.text(1, 0.9, "END", ha="right", va="bottom", fontsize=7, color=_GREY)
    ax.annotate(
        f"YOU  {start:.0f} mi", (frac0, 0), (frac0, -0.9),
        ha="center", va="top", fontsize=7, color=_RED, fontweight="bold",
    )


def _next_decisions(route: Route, after_mile: float) -> list[DecisionPoint]:
    upcoming = [d for d in route.decision_points if d.mile > after_mile + 1e-6]
    return sorted(upcoming, key=lambda d: d.mile)


def _next_fuel(route: Route, after_mile: float) -> FuelStop | None:
    upcoming = [f for f in route.fuel_stops if f.mile >= after_mile - 1e-6]
    return min(upcoming, key=lambda f: f.mile) if upcoming else None


def _draw_cue_zone(fig, route: Route, start: float, total: float) -> None:
    decisions = _next_decisions(route, start)
    nxt = decisions[0] if decisions else None
    after = decisions[1] if len(decisions) > 1 else None
    fuel = _next_fuel(route, start)

    def block(x, label, big, sub, color="#111111"):
        fig.text(x, 0.235, label, ha="left", va="top", fontsize=12, color=_GREY, fontweight="bold")
        fig.text(x, 0.175, big, ha="left", va="top", fontsize=19, color=color, fontweight="bold")
        if sub:
            fig.text(x, 0.085, _wrap(sub, 24), ha="left", va="top", fontsize=11, color=color)

    if nxt:
        block(0.04, "NEXT", f"{nxt.mile - start:.1f} mi", nxt.instruction, _RED)
    else:
        block(0.04, "NEXT", "Arrive", "End of route", _RED)
    if after:
        block(0.30, "AFTER", f"{after.mile - start:.1f} mi", after.instruction)
    if fuel:
        block(0.58, "FUEL", _wrap(fuel.name, 14), f"in {fuel.mile - start:.0f} mi", _BLUE)
    block(0.84, "TOTAL", f"{start:.0f} / {total:.0f}", "miles")


def _wrap(text: str, width: int) -> str:
    """Soft-wrap ``text`` to at most ``width`` chars per line, on word breaks."""
    words = text.split()
    lines: list[str] = [""]
    for w in words:
        if lines[-1] and len(lines[-1]) + 1 + len(w) > width:
            lines.append(w)
        else:
            lines[-1] = f"{lines[-1]} {w}".strip()
    return "\n".join(lines)


def generate_pdf(
    gpx_file: str,
    output_file: str = "route.pdf",
    *,
    profile: str = "sport-touring",
    fuel_range: float | None = None,
    use_osm: bool = False,
    turn_style: str = TURN_STYLE_STYLIZED,
) -> str:
    """Load, analyze, and render a route to a tank-bag PDF."""
    from .analysis import analyze_route
    from .gpx import load_route

    route = analyze_route(
        load_route(gpx_file), profile=profile, fuel_range=fuel_range, use_osm=use_osm
    )
    render_pdf(route, output_file, turn_style=turn_style)
    return str(output_file)
