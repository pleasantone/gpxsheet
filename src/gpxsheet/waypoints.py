"""Waypoint classification: map a stop's name/symbol to trip-planning semantics.

Ported from GPXtable's ``GPXTABLE_DEFAULT_WAYPOINT_CLASSIFIER`` so the native
route table (:mod:`gpxsheet.routetable`) can assign each stop a layover delay, a
``G``/``L``/``GL`` marker and a fuel-reset flag without depending on
GPXtable's classes. The rule schema is kept **identical to GPXtable's** (the same
``symbol``/``search``/``delay``/``marker``/``fuel_reset`` keys) so a GPXtable
``--config`` JSON file is interchangeable here.

A rule matches when the waypoint's ``symbol`` equals the rule's ``symbol`` *or*
the rule's ``search`` regex matches the waypoint name (case-insensitive); the
first match in list order wins and a name match adopts the rule's symbol. This
mirrors :meth:`gpxtable.GPXPointMixin._classify`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# The default classifier. Identical in meaning to GPXtable's default, with one
# fix: the Restaurant ``search`` had ``\b\Dinner\b`` -- ``\D`` is "any non-digit",
# so it matched "winner"/"sinner" as lunch stops. Corrected to ``\bDinner\b``.
#
# The ``(G)``/``(L)``/``(R)``/``(P)`` parenthetical shorthands are kept verbatim
# from GPXtable, including its quirk that ``\b\(G\)\b`` only matches when the
# token is glued to word characters (``(`` is not a word char, so the leading
# ``\b`` rarely fires) -- preserved so GPXtable remains an exact parity oracle.
DEFAULT_CLASSIFIER: list[dict[str, Any]] = [
    {
        "symbol": "Gas/Restaurant",
        "search": r"(?=.*\b(Gas|Fuel)\b)(?=.*\b(Lunch|Meal)\b)",
        "delay": 75,
        "marker": "GL",
        "fuel_reset": True,
    },
    {
        "symbol": "Gas Station",
        "search": r"\bGas\b|\bFuel\b|\b\(G\)\b",
        "delay": 15,
        "marker": "G",
        "fuel_reset": True,
    },
    {
        "symbol": "Restaurant",
        "search": r"\bRestaurant\b|\bLunch\b|\bBreakfast\b|\bDinner\b|\b\(L\)\b",
        "delay": 60,
        "marker": "L",
    },
    {
        "symbol": "Restroom",
        "search": r"\bRestroom\b|\bBreak\b|\b\(R\)\b",
        "delay": 15,
    },
    {
        "symbol": "Scenic Area",
        "delay": 5,
    },
    {"symbol": "Photo", "search": r"\bPhotos?\b|\b\(P\)\b", "delay": 5},
]


@dataclass(frozen=True, slots=True)
class Classification:
    """The trip-planning semantics resolved for a waypoint.

    ``symbol`` is the effective symbol (the rider's symbol, or the one adopted
    from a name-regex match); ``delay`` is the layover in minutes; ``marker`` is
    the ``G``/``L``/``GL`` (or empty) column flag; ``fuel_reset`` resets the
    distance-since-fuel counter.
    """

    symbol: str | None
    delay: int = 0
    marker: str = ""
    fuel_reset: bool = False


def classify(
    name: str | None,
    symbol: str | None,
    classifier: list[dict[str, Any]] | None = None,
) -> Classification:
    """Resolve a waypoint's :class:`Classification` (first matching rule wins).

    A rule matches on an exact ``symbol`` equality or a case-insensitive
    ``search`` regex over ``name``; on a name match the rule's symbol is adopted.
    Falls back to a no-op classification (the original symbol, no delay/marker)
    when nothing matches.
    """
    rules = classifier if classifier is not None else DEFAULT_CLASSIFIER
    for rule in rules:
        matched_symbol = symbol is not None and symbol == rule.get("symbol")
        matched_name = "search" in rule and bool(
            re.search(rule["search"], name or "", re.I)
        )
        if matched_symbol or matched_name:
            return Classification(
                symbol=rule.get("symbol") if matched_name else symbol,
                delay=int(rule.get("delay", 0)),
                marker=str(rule.get("marker", "")),
                fuel_reset=bool(rule.get("fuel_reset", False)),
            )
    return Classification(symbol=symbol)
