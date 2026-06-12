"""The service analysis cache reuses one analyze_core across operations."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("fastapi")  # service extra

from gpxsheet import analysis  # noqa: E402
from gpxsheet.service import analysis_cache  # noqa: E402


def _count_core(monkeypatch):
    calls = {"n": 0}
    real = analysis.analyze_core

    def counting(route, **kw):
        calls["n"] += 1
        return real(route, **kw)

    monkeypatch.setattr(analysis, "analyze_core", counting)
    return calls


def test_core_computed_once_per_gpx_and_osm(enrich_route_file, monkeypatch):
    analysis_cache.clear()
    calls = _count_core(monkeypatch)
    gpx = enrich_route_file.read_bytes()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = analysis_cache.get_core(gpx, osm=True)
        b = analysis_cache.get_core(gpx, osm=True)  # render + table + analyze reuse

    assert a is b  # same cached object
    assert calls["n"] == 1  # OSM/analysis ran once, not per operation

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        analysis_cache.get_core(gpx, osm=False)  # a different analysis variant
    assert calls["n"] == 2


def test_derive_does_not_mutate_cached_core(enrich_route_file):
    analysis_cache.clear()
    gpx = enrich_route_file.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        core = analysis_cache.get_core(gpx, osm=True)
    before = len(core.decision_points)
    # A restrictive profile filters decisions in the derived route...
    derived = analysis.derive_products(core, profile="minimalist")
    assert len(derived.decision_points) <= before
    # ...but the shared core is untouched, so the next op still sees the full set.
    assert len(core.decision_points) == before
