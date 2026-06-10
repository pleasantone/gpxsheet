"""Text rendering of a route analysis (the ``analyze`` output mode).

Mirrors the example in docs/product.md's "Analyze" section.
"""

from __future__ import annotations

from .models import Route


def format_analysis(route: Route) -> str:
    lines: list[str] = []
    lines.append(f"Route: {route.name}")
    lines.append(f"Route Length: {route.length_miles:.1f} mi")
    lines.append("")

    lines.append("Decision Points:")
    if route.decision_points:
        for dp in route.decision_points:
            lines.append(f"  {dp.mile:6.1f}  {dp.instruction}  (sig {dp.significance})")
    else:
        lines.append("  (none above threshold)")
    lines.append("")

    if route.fuel_stops:
        lines.append("Fuel:")
        for fs in route.fuel_stops:
            lines.append(f"  {fs.mile:6.1f}  {fs.name}")
        lines.append("")

    if route.fuel_report is not None:
        lines.append("Longest Fuel Gap:")
        lines.append(f"  {route.fuel_report.longest_gap_miles:.0f} mi")
        if route.fuel_report.exceeds_range:
            lines.append(
                f"  ⚠ exceeds configured fuel range of "
                f"{route.fuel_report.fuel_range_miles:.0f} mi"
            )
        lines.append("")

    if route.reassurance_markers:
        lines.append("Reassurance Markers:")
        for m in route.reassurance_markers:
            lines.append(f"  {m.mile:6.1f}  {m.label}")
        lines.append("")

    lines.append("Road Segments:")
    for seg in route.segments:
        lines.append(f"  {seg.name}  ({seg.length_miles:.1f} mi)")

    return "\n".join(lines)
