"""GPXSheet web service (Milestone 5).

A FastAPI app that exposes the engine over REST: upload a GPX, get a tank-bag PDF.
Renders are slow (matplotlib + live OSM), so generation runs as a background job
(Dramatiq + Redis) with the result stored in object storage (MinIO); a synchronous
``/v1/analyze`` returns the structured route analysis as JSON.

Requires the ``service`` extra: ``pip install "gpxsheet[service]"`` (add ``osm``
for road-name enrichment).
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Lazy re-export so importing the subpackage doesn't require FastAPI."""
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)
