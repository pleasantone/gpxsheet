"""MkDocs build hooks.

Regenerates ``docs/openapi.json`` from the live FastAPI app on every build so the
interactive Web API reference (rendered by swagger-ui-tag) never drifts from the
code. Generation needs no server and no network: ``create_app()`` with no Redis
configured uses the in-memory/eager dev path, and ``app.openapi()`` is pure.
"""

from __future__ import annotations

import json
from pathlib import Path


def on_pre_build(config) -> None:  # noqa: ARG001 - MkDocs hook signature
    from gpxsheet.service.app import create_app

    schema = create_app().openapi()
    out = Path(__file__).parent / "openapi.json"
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
