"""ASGI entrypoint: ``uvicorn gpxsheet.service.asgi:app``.

Components are chosen from the environment (see :mod:`gpxsheet.service.settings`):
Redis + MinIO + Dramatiq when ``GPXSHEET_REDIS_URL`` is set, otherwise a
single-process in-memory dev server. The Dramatiq worker runs separately:
``dramatiq gpxsheet.service.jobs``.
"""

from __future__ import annotations

from .app import create_app

app = create_app()
