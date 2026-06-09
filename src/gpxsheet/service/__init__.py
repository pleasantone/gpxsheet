"""GPXSheet web service.

A FastAPI app that exposes the engine over REST. Every operation is a background
job (Dramatiq + Redis) with the result stored in object storage (MinIO): POST to a
typed endpoint (``/v1/render`` -- picks a ``layout`` and ``format``; ``/v1/analyze``
and ``/v1/validate`` -- JSON reports), poll ``GET /v1/jobs/{id}``, then fetch
``.../result``.

Requires the ``service`` extra: ``pip install "gpxsheet[service]"``.
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Lazy re-export so importing the subpackage doesn't require FastAPI."""
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)
