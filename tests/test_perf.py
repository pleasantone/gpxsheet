"""Tests for the perf instrumentation (src/gpxsheet/perf.py)."""

from __future__ import annotations

import logging

from gpxsheet import perf


def test_track_logs_one_summary_with_spans_and_meta(caplog):
    with caplog.at_level(logging.INFO, logger="gpxsheet.perf"):
        with perf.track("job:test", bytes="11KB"):
            perf.annotate(cache="miss")
            with perf.span("load"):
                pass
            with perf.span("render"):
                pass

    lines = [r.getMessage() for r in caplog.records if r.name == "gpxsheet.perf"]
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("perf job:test")
    assert "bytes=11KB" in line and "cache=miss" in line  # meta
    assert "load=" in line and "render=" in line  # spans


def test_span_and_annotate_outside_track_are_safe():
    # No active track: a span just times (no record kept, no error); annotate no-ops.
    with perf.span("orphan"):
        pass
    perf.annotate(foo="bar")  # must not raise


def test_track_is_isolated_after_exit(caplog):
    with caplog.at_level(logging.INFO, logger="gpxsheet.perf"):
        with perf.track("first"):
            with perf.span("a"):
                pass
        # This span is outside any track -> not attributed to "first".
        with perf.span("loose"):
            pass
        with perf.track("second"):
            with perf.span("b"):
                pass

    lines = [r.getMessage() for r in caplog.records if r.name == "gpxsheet.perf"]
    assert any(m.startswith("perf first") and "a=" in m and "loose" not in m for m in lines)
    assert any(m.startswith("perf second") and "b=" in m and "a=" not in m for m in lines)
