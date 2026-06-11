"""Default values for the public render knobs, in one place.

A render default is changed by editing a single line here, not by re-declaring
the literal at every layer (library ``render``, CLI, web service, and the
``pdf``/``strip`` renderers). Kept deliberately import-cheap (only ``layout``,
which is pure geometry) so any layer can import it freely.
"""

from __future__ import annotations

from .layout import TURN_STYLE_STYLIZED

DEFAULT_PROFILE = "sport-touring"  # minimalist | sport-touring | rally
DEFAULT_LAYOUT = "portrait"        # portrait | landscape | preview | strip
DEFAULT_FORMAT = "pdf"             # pdf | png
SHOW_BRANCHES = False  # ghosted "roads not taken" stubs off by default
TURN_STYLE = TURN_STYLE_STYLIZED  # "stylized" vs "faithful"
PAPER = "letter"  # vs "a4"
LANES_PER_PAGE = 4  # portrait stacked strips per page
# Public default = auto-fit (0 packs each lane until labels would overlap).
# The pdf renderers keep a separate internal fixed-cap fallback
# (``pdf.FIXED_DECISIONS_PER_LANE``) for direct calls.
DECISIONS_PER_LANE = 0
