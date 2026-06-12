"""ASGI entrypoint: ``uvicorn gpxsheet.service.asgi:app``.

Components are chosen from the environment (see :mod:`gpxsheet.service.settings`):
Redis + MinIO + Dramatiq when ``GPXSHEET_REDIS_URL`` is set, otherwise a
single-process in-memory dev server. The Dramatiq worker runs separately:
``dramatiq gpxsheet.service.jobs``.
"""

from __future__ import annotations

import logging

from .app import create_app


def _ensure_logging() -> None:
    """Surface ``gpxsheet`` INFO logs (incl. the ``gpxsheet.perf`` job lines).

    uvicorn configures only its own loggers, so app INFO would otherwise be
    dropped. Set the ``gpxsheet`` logger to INFO and, only when nothing else has
    configured logging, attach one stderr handler. Propagation stays on, so a
    deployment that configures the root logger (or pytest's ``caplog``) still sees
    the records and there's no double output.
    """
    gpxsheet_log = logging.getLogger("gpxsheet")
    gpxsheet_log.setLevel(logging.INFO)
    if not logging.getLogger().handlers and not gpxsheet_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        gpxsheet_log.addHandler(handler)


_ensure_logging()
app = create_app()
