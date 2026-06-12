"""In-process cache of the profile-independent analysis core.

Every web operation (render/table/analyze/validate) needs the *same* expensive
analyzed Route for a given GPX -- only cheap profile/display gating differs. So
the SPA firing analyze + preview + render for one drop, or switching tabs, used
to re-run OSM enrichment several times over identical geometry.

This caches :func:`gpxsheet.analysis.analyze_core` keyed on
``(sha256(gpx_bytes), osm)``, so the Overpass work runs **once per file** and
every later operation derives its products from the cached core. Single-flight
(one in-flight compute per key) stops the SPA's concurrent first-drop jobs from
all missing and each doing the OSM pass.

The cache is in-process: it fully covers the single-process dev / eager / Hugging
Face path. Under multi-worker Dramatiq each worker keeps its own cache (still
cuts repeats within a worker); cross-worker sharing would need the core persisted
to Redis, which is a later step.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpxsheet.models import Route

# Each cached Route holds the full point list, so keep the cache small + bounded.
_MAXSIZE = 16

_Key = tuple[str, bool]
_lock = threading.Lock()
_cache: OrderedDict[_Key, Route] = OrderedDict()
_keylocks: dict[_Key, threading.Lock] = {}


def _compute(gpx_bytes: bytes, osm: bool) -> Route:
    from gpxsheet.analysis import analyze_core
    from gpxsheet.gpx import load_route

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "route.gpx"
        path.write_bytes(gpx_bytes)
        return analyze_core(load_route(str(path)), osm=osm)


def get_core(gpx_bytes: bytes, *, osm: bool) -> Route:
    """The cached :func:`analyze_core` Route for ``(gpx_bytes, osm)``.

    Callers must treat the returned core as read-only (derive a fresh Route via
    :func:`gpxsheet.analysis.derive_products`); it is shared across requests.
    """
    key: _Key = (hashlib.sha256(gpx_bytes).hexdigest(), osm)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
        keylock = _keylocks.setdefault(key, threading.Lock())

    # Single-flight: only the first caller computes; the rest wait, then hit cache.
    with keylock:
        with _lock:
            hit = _cache.get(key)
            if hit is not None:
                _cache.move_to_end(key)
                return hit
        route = _compute(gpx_bytes, osm)
        with _lock:
            _cache[key] = route
            _cache.move_to_end(key)
            while len(_cache) > _MAXSIZE:
                _cache.popitem(last=False)
            _keylocks.pop(key, None)
        return route


def clear() -> None:
    """Drop all cached analyses (used by tests)."""
    with _lock:
        _cache.clear()
        _keylocks.clear()
