"""Lightweight per-request performance instrumentation.

Wrap a unit of work in :func:`track`; inside it, time sub-steps with :func:`span`
and attach context with :func:`annotate`. On exit a single structured ``INFO``
line is logged (logger ``gpxsheet.perf``) with the total and every span, so a slow
job shows exactly which phase -- cache miss, OSM enrich, derive, render -- cost
the time, e.g.::

    perf job:render 2.34s [bytes=1.7MB points=30909 cache=miss] load=0.10
        geometry=0.42 enrich=0.00 derive.pois=0.31 derive.reassurance=0.30 render=1.16

Spans nest via a :class:`~contextvars.ContextVar`, so library code (analysis,
cache, render) records into whatever job is active without passing a recorder
through call signatures. Outside any :func:`track` a span is ~free (a
``perf_counter`` and, only at DEBUG, a log line).
"""

from __future__ import annotations

import contextvars
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

log = logging.getLogger("gpxsheet.perf")


class _Record:
    __slots__ = ("label", "spans", "meta")

    def __init__(self, label: str) -> None:
        self.label = label
        self.spans: list[tuple[str, float]] = []
        self.meta: dict[str, object] = {}


_current: contextvars.ContextVar[_Record | None] = contextvars.ContextVar(
    "gpxsheet_perf", default=None
)


def annotate(**meta: object) -> None:
    """Attach ``key=value`` context (e.g. ``cache="hit"``) to the active track."""
    record = _current.get()
    if record is not None:
        record.meta.update(meta)


@contextmanager
def span(name: str) -> Iterator[None]:
    """Time a sub-step, recording it on the active track (else a DEBUG line)."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        record = _current.get()
        if record is not None:
            record.spans.append((name, elapsed))
        elif log.isEnabledFor(logging.DEBUG):
            log.debug("%s %.3fs", name, elapsed)


@contextmanager
def track(label: str, **meta: object) -> Iterator[_Record]:
    """Time a whole unit of work; log one summary line (total + spans) on exit."""
    record = _Record(label)
    record.meta.update(meta)
    token = _current.set(record)
    start = time.perf_counter()
    try:
        yield record
    finally:
        _current.reset(token)
        total = time.perf_counter() - start
        log.info(
            "perf %s %.3fs%s%s",
            label, total, _fmt_meta(record.meta), _fmt_spans(record.spans),
        )


def _fmt_meta(meta: dict[str, object]) -> str:
    return " [" + " ".join(f"{k}={v}" for k, v in meta.items()) + "]" if meta else ""


def _fmt_spans(spans: list[tuple[str, float]]) -> str:
    return " " + " ".join(f"{n}={s:.3f}" for n, s in spans) if spans else ""
