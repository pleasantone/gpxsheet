"""Smoke tests for the GPXSheet scaffold."""

import pytest

import gpxsheet
from gpxsheet.cli import app


def test_version_is_exposed():
    assert isinstance(gpxsheet.__version__, str)
    assert gpxsheet.__version__.count(".") >= 1


def test_cli_app_imports():
    # The Typer app object should be constructed without error.
    assert app is not None


def test_generate_pdf_not_implemented_yet():
    with pytest.raises(NotImplementedError):
        gpxsheet.generate_pdf("nope.gpx")


def test_analyze_not_implemented_yet():
    with pytest.raises(NotImplementedError):
        gpxsheet.analyze("nope.gpx")
