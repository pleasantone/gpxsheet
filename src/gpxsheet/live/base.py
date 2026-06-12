"""Live-data provider plumbing for day cards (Phase 2).

A *provider* fetches one kind of planning-time live data (weather, air quality,
elevation, wildfire) for a route + its per-day sample points. The contract is
**graceful**: any failure -- no API key, network down, past the forecast
horizon, an offline cache miss -- degrades to ``None`` (the card omits that
section, with a note) rather than raising. Every HTTP response is cached on disk
so adjacent days and repeated runs don't hammer the upstream service.

Determinism: the test suite runs **cache-only** against a committed
``tests/fixtures/live_cache`` (a miss returns ``None``); record real
fixtures with ``GPXSHEET_RECORD_LIVE=1``. ``GPXSHEET_DISABLE_LIVE=1`` (or the
umbrella ``GPXSHEET_OFFLINE=1``) forces static-only -- the user-facing switch.

These are the ``LIVE`` source's knobs in the shared ``GPXSHEET_*`` convention
(see :mod:`gpxsheet.sources`): ``GPXSHEET_LIVE_CACHE_DIR`` (cache location),
``GPXSHEET_DISABLE_LIVE`` / ``GPXSHEET_OFFLINE`` (force static-only),
``GPXSHEET_RECORD_LIVE`` (allow + persist live fetches), and per-provider
``GPXSHEET_<PROVIDER>_BASE_URL`` overrides (self-host / proxy / test).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..sources import live_disabled

log = logging.getLogger("gpxsheet.live")

# Default per-request HTTP timeout (seconds); short so a slow upstream degrades
# the card quickly rather than holding a web job past a proxy timeout.
HTTP_TIMEOUT_S = 20.0


@dataclass(slots=True)
class SamplePoint:
    """One point sampled along a day for live lookups.

    ``time`` is the interpolated ETA (tz-aware) or ``None`` when the day has no
    departure; ``heading`` is the route bearing through the point (for crosswind).
    """

    mile: float
    lat: float
    lon: float
    time: datetime | None = None
    heading: float | None = None


def cache_dir() -> Path:
    """The on-disk response cache directory (``GPXSHEET_LIVE_CACHE_DIR``)."""
    override = os.getenv("GPXSHEET_LIVE_CACHE_DIR")
    base = Path(override) if override else Path(tempfile.gettempdir()) / "gpxsheet_live_cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cache_key(provider: str, url: str, params: dict[str, Any]) -> str:
    """A stable filename stem for a request (provider + URL + sorted params)."""
    blob = json.dumps([provider, url, sorted(params.items())], sort_keys=True, default=str)
    digest = hashlib.sha1(blob.encode()).hexdigest()[:16]
    return f"{provider}_{digest}"


def _http_get_json(url: str, params: dict[str, Any]) -> Any:
    """GET ``url?params`` and parse JSON. The single network seam tests patch."""
    query = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{query}" if query else url
    req = urllib.request.Request(full, headers={"User-Agent": "gpxsheet/day-cards"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # noqa: S310 - https only
        return json.loads(resp.read().decode("utf-8"))


def fetch_json(provider: str, url: str, params: dict[str, Any]) -> Any | None:
    """Fetch JSON for a provider request, cached on disk; ``None`` on any failure.

    Order: force-disabled → ``None``; cache hit → the stored response; miss →
    a live GET (only when recording, or in normal non-test use) that is then
    cached. Tests patch :func:`_http_get_json` to a cache-only stand-in, so a
    miss there returns ``None`` and the section is skipped.
    """
    if live_disabled():
        return None
    key = _cache_key(provider, url, params)
    path = cache_dir() / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("providers: unreadable cache file %s; refetching", path)
    try:
        data = _http_get_json(url, params)
    except Exception as exc:  # noqa: BLE001 - any failure degrades to "unavailable"
        log.info("providers: %s fetch failed (%s); section unavailable", provider, exc)
        return None
    if data is None:
        return None
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        log.warning("providers: could not cache %s response: %s", provider, exc)
    return data


class Provider:
    """Base for a live-data provider.

    Subclasses set :attr:`name`, an optional :attr:`requires_key` env var (when
    set and missing the provider is unavailable -- key-gated, Phase 3), and an
    optional :attr:`base_url_env` override of :attr:`default_base_url`.
    """

    name: str = ""
    requires_key: str | None = None
    base_url_env: str | None = None
    default_base_url: str = ""

    def api_key(self) -> str | None:
        return os.getenv(self.requires_key) if self.requires_key else None

    def base_url(self) -> str:
        if self.base_url_env:
            return os.getenv(self.base_url_env) or self.default_base_url
        return self.default_base_url

    def available(self) -> bool:
        """Whether a fetch could succeed: live enabled and (if gated) keyed."""
        if live_disabled():
            return False
        if self.requires_key and not self.api_key():
            return False
        return True

    def get_json(self, params: dict[str, Any], *, path: str = "") -> Any | None:
        """Cached GET against this provider's base URL + ``path``."""
        return fetch_json(self.name, self.base_url() + path, params)
