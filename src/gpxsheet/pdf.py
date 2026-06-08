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
from .models import Route
from .paginate import paginate, slice_route
from .strip import draw_strip

_RED = "#d6312b"
_GREEN = "#1b7837"
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

    _draw_header(fig, route.name, page_no, page_count, start, total)
    _draw_progress(fig, start, end, total)

    # Map zone (option b): the framed panel HUGS the strip (height = the strip's
    # natural aspect-preserving height + the ribbon + a small margin) and the whole
    # panel is centered in the area below the header/progress bar -- so there's no
    # big empty box around a flat strip. Panel size/position varies per page.
    from matplotlib.patches import Rectangle

    avail_lo, avail_hi = 0.05, 0.86  # vertical area below the progress bar
    panel_x, panel_w = 0.03, 0.94
    margin, ribbon_band = 0.018, 0.030  # inner pad; room for the ribbon at bottom

    span_x = 1.24 * (layout.width or 1.0)
    span_y = 1.6 * (layout.height or 0.0) + 2.0
    aspect = span_x / span_y
    map_w = panel_w - 0.02
    map_h = (map_w * 11.0 / aspect) / 8.5
    map_h = max(0.12, min(map_h, (avail_hi - avail_lo) - 2 * margin - ribbon_band))

    panel_h = map_h + 2 * margin + ribbon_band
    panel_bottom = (avail_lo + avail_hi) / 2 - panel_h / 2  # center the panel
    map_y = panel_bottom + margin + ribbon_band

    fig.patches.append(
        Rectangle(
            (panel_x, panel_bottom), panel_w, panel_h, transform=fig.transFigure,
            facecolor="#fafafa", edgecolor="#dddddd", linewidth=1.0, zorder=-10,
        )
    )
    map_ax = fig.add_axes([panel_x + 0.01, map_y, map_w, map_h])
    draw_strip(fig, map_ax, layout, draw_ribbon=False)
    ribbon = "  ›  ".join(layout.ribbon)
    if ribbon:
        fig.text(
            0.5, panel_bottom + 0.012, ribbon, ha="center", va="bottom",
            fontsize=8, color="#444444",
        )


def _draw_header(fig, name: str, page_no: int, page_count: int, start: float, total: float) -> None:
    # Truncate long route names (GPX often auto-names "<start> to <end>") so the
    # title never runs into the mileage / page counter.
    display = name if len(name) <= 48 else name[:47].rstrip() + "…"
    fig.text(0.03, 0.955, display, ha="left", va="center", fontsize=13, fontweight="bold")
    fig.text(
        0.84, 0.955, f"{start:.0f} / {total:.0f} mi",
        ha="right", va="center", fontsize=11, color=_GREEN, fontweight="bold",
    )
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
