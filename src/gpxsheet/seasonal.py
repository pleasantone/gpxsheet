"""Seasonal-closure detection for the ``validate`` hazard report.

Many sport-touring roads — Sierra/Cascade passes especially — close over winter,
so a route that looks fine in July is impassable in March. This is a *hybrid*
check:

* a **curated list** of well-known seasonal roads (:data:`SEASONAL_ROADS`),
  matched against the OSM road names/refs on ``route.segments`` — reliable for the
  passes riders actually care about, and needs no extra Overpass query; and
* an **OSM-tag supplement** (:func:`is_seasonal_edge`) reading per-edge
  ``seasonal`` / ``*:conditional`` / ``snowmobile`` tags during enrichment, for
  seasonal roads not in the curated list.

Both feed ``Route.seasonal_closures`` (see :mod:`gpxsheet.enrich`), which
:func:`gpxsheet.validate.validate_route` turns into a warning. The matching is
advisory: it flags the *risk* and tells the rider to verify, rather than asserting
a specific open/closed date (the validate path carries no trip date).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Curated seasonal roads: a set of match tokens (OSM name/ref variants, already
# normalized by :func:`_normalize`) -> a human label with the typical window. A
# deliberately small, extensible seed list of well-known, reliably-seasonal roads.
SEASONAL_ROADS: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"ca 120", "tioga pass", "tioga road"}),
     "Tioga Pass (CA-120) — typically closed Nov–May"),
    (frozenset({"ca 108", "sonora pass"}),
     "Sonora Pass (CA-108) — typically closed in winter"),
    (frozenset({"ca 4", "ebbetts pass"}),
     "Ebbetts Pass (CA-4) — typically closed in winter"),
    (frozenset({"ca 89", "monitor pass"}),
     "Monitor Pass (CA-89) — typically closed in winter"),
    (frozenset({"ca 180", "kings canyon road", "kings canyon highway"}),
     "Kings Canyon / Cedar Grove (CA-180) — typically closed in winter"),
    (frozenset({"wa 20", "north cascades highway"}),
     "North Cascades Highway (WA-20) — typically closed Nov–Apr"),
    (frozenset({"or 242", "mckenzie highway", "mckenzie pass"}),
     "McKenzie Pass (OR-242) — typically closed in winter"),
    (frozenset({"us 212", "beartooth highway", "beartooth pass"}),
     "Beartooth Highway (US-212) — typically closed mid-Oct–May"),
    (frozenset({"us 34", "trail ridge road"}),
     "Trail Ridge Road (US-34) — typically closed Oct–May"),
    (frozenset({"going to the sun road"}),
     "Going-to-the-Sun Road — typically closed mid-Oct–June"),
)

# Month / season / snow tokens that mark a ``*:conditional`` access value as a
# seasonal restriction (vs. a time-of-day-only one, which we ignore).
_SEASON_TOKENS = frozenset(
    {
        "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
        "winter", "spring", "summer", "autumn", "fall", "snow",
    }
)


def _normalize(s: str) -> str:
    """Lowercase and collapse non-alphanumerics to single spaces (``CA-120`` -> ``ca 120``)."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _token_in(token: str, name: str) -> bool:
    """Whole-token match so ``ca 1`` does not match ``ca 120`` (word boundaries)."""
    return re.search(rf"\b{re.escape(token)}\b", name) is not None


def curated_closures(segment_names: Iterable[str]) -> list[str]:
    """Labels for curated seasonal roads whose name/ref appears in ``segment_names``.

    Each road contributes its label at most once; results follow
    :data:`SEASONAL_ROADS` order.
    """
    norm = [_normalize(n) for n in segment_names if n]
    return [
        label
        for tokens, label in SEASONAL_ROADS
        if any(_token_in(tok, nn) for tok in tokens for nn in norm)
    ]


def _conditional_is_seasonal(value: str | None) -> bool:
    """True if a ``*:conditional`` access value is gated on a month/season/snow token."""
    if not value:
        return False
    norm = _normalize(value)
    return any(tok in norm.split() for tok in _SEASON_TOKENS)


def is_seasonal_edge(
    seasonal: str | None = None,
    access_conditional: str | None = None,
    motor_vehicle_conditional: str | None = None,
    snowmobile: str | None = None,
) -> bool:
    """Whether an OSM edge's tags mark it as a seasonally-restricted road.

    Conservative: a plain time-of-day ``access:conditional`` (no month/season token)
    is **not** treated as seasonal.
    """
    if (seasonal or "").strip().lower() not in ("", "no"):
        return True
    if (snowmobile or "").strip().lower() in ("designated", "yes", "official"):
        return True
    return _conditional_is_seasonal(access_conditional) or _conditional_is_seasonal(
        motor_vehicle_conditional
    )
