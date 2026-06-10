"""Shared color palette for the schematic renderers (``strip`` and ``pdf``).

Names describe what each color is *for*, not its hue, so call sites read clearly
(``color=colors.FUEL`` instead of ``color="#2166ac"``). Keeping the palette in
one place also keeps the strip and the PDF visually consistent — the same red
means "a decision / where you are" in both. Hex values are noted inline.

The visual language: **red** = something you act on or your current position,
**green** = start / progress, plus distinct hues for end, fuel, and reassurance.
"""

from __future__ import annotations

# Route geometry
ROUTE_LINE = "#333333"  # the drawn route ribbon (strip)
UNPAVED_RIBBON = "#8b5a2b"  # unpaved/gravel stretches (brown, dashed)
FERRY_RIBBON = "#1f6feb"  # ferry crossings (blue, dashed)

# Marker / accent colors, by role.
START = "#1b7837"  # start marker; also PDF page-mileage + segment-name labels
END = "#762a83"  # end marker (plum)
DECISION = "#d6312b"  # decision points + roundabout ring; also PDF "YOU" / current-page accent
FUEL = "#2166ac"  # fuel stops (blue)
FOOD = "#d2691e"  # food / rest stops (chocolate orange)
WAYPOINT = "#8a6d3b"  # generic named rider waypoints (brown)
REASSURANCE = "#7f7f7f"  # reassurance ticks (grey)
REASSURANCE_TOWN = "#3a6b6b"  # named town/landmark reassurance labels (muted teal)
MARKER_FALLBACK = "#000000"  # unknown marker kind

# PDF map-zone panel
PANEL_FILL = "#fafafa"  # map-zone background
PANEL_EDGE = "#dddddd"  # map-zone border

# PDF progress bar
PROGRESS_TRACK = "#cccccc"  # full-route bar behind the red current-page segment

# Text
TEXT_LABEL = "#444444"  # marker / cue / segment labels
TEXT_MUTED = "#666666"  # secondary text (START/END captions, page counter)

# Auxiliary lines
BRANCH_STUB = "#bbbbbb"  # ghosted roads-not-taken stubs
LEADER_LINE = "#999999"  # dashed leader lines from a marker to its label
