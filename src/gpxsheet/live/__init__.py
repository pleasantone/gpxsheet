"""Live-data providers for day cards (Phase 2).

Keyless, cached, graceful sources of planning-time conditions: Open-Meteo
weather / air-quality / elevation and NIFC wildfire perimeters. Every provider
degrades to ``None`` on any failure and caches responses on disk; see
:mod:`gpxsheet.live.base` for the cache + offline switches (and
:mod:`gpxsheet.sources` for the shared external-data env convention).
"""

from __future__ import annotations

from .air import AirInfo, fetch_air
from .base import SamplePoint, cache_dir, live_disabled
from .elevation import ElevationProfile, fetch_elevation
from .fire import Fire, fetch_fires
from .weather import WeatherInfo, WeatherSample, fetch_weather

__all__ = [
    "AirInfo",
    "ElevationProfile",
    "Fire",
    "SamplePoint",
    "WeatherInfo",
    "WeatherSample",
    "cache_dir",
    "fetch_air",
    "fetch_elevation",
    "fetch_fires",
    "fetch_weather",
    "live_disabled",
]
