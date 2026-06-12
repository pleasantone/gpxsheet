"""Shared conventions for GPXSheet's external data sources.

Two subsystems reach out over the network, and they're deliberately *different
animals*: the **OSM** enrichment core (osmnx -> Overpass, building graphs +
GeoDataFrames; mandatory, with a geometry-only fallback) and the day-card **live**
providers (Open-Meteo / NIFC, plain JSON GETs; optional, omitted when down). They
do not share an implementation -- but they do share four operational concerns,
each governed by a *regular* ``GPXSHEET_*`` environment variable so the two read
as siblings:

    GPXSHEET_<SRC>_CACHE_DIR   on-disk response cache location
    GPXSHEET_<SRC>_BASE_URL    endpoint override (self-host / proxy / mirror)
    GPXSHEET_DISABLE_<SRC>     skip the network (degrade gracefully)
    GPXSHEET_RECORD_<SRC>      record fixtures (test harness)

``<SRC>`` is ``OSM`` for the Overpass/osmnx core and ``LIVE`` for the day-card
providers. Two intentional exceptions: the OSM endpoint override keeps its
precise name ``GPXSHEET_OVERPASS_BASE_URL`` (it's specifically the Overpass
endpoint), and each live provider has its own ``GPXSHEET_<PROVIDER>_BASE_URL``
(weather/air/elevation/fire share one cache + one disable, but distinct URLs).

``GPXSHEET_OFFLINE`` is the umbrella: it implies *every* ``GPXSHEET_DISABLE_<SRC>``
at once -- one switch for air-gapped boxes or deterministic CI.
"""

from __future__ import annotations

import os


def _flag(name: str) -> bool:
    """A truthy env flag: ``1`` / ``true`` / ``yes`` (case-insensitive)."""
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def offline() -> bool:
    """Umbrella switch: skip *all* network sources (implies every DISABLE_*)."""
    return _flag("GPXSHEET_OFFLINE")


def osm_disabled() -> bool:
    """Whether OSM/Overpass enrichment is opted out (geometry-only fallback)."""
    return offline() or _flag("GPXSHEET_DISABLE_OSM")


def live_disabled() -> bool:
    """Whether the day-card live providers are opted out (sections omitted)."""
    return offline() or _flag("GPXSHEET_DISABLE_LIVE")


def recording_live() -> bool:
    """Whether live-provider fetches are allowed and persisted to the cache."""
    return _flag("GPXSHEET_RECORD_LIVE")
