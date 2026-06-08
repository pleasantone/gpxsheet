"""Smoke tests for the GPXSheet scaffold."""

import gpxsheet
from gpxsheet.cli import app


def test_version_is_exposed():
    assert isinstance(gpxsheet.__version__, str)
    assert gpxsheet.__version__.count(".") >= 1


def test_cli_app_imports():
    # The Typer app object should be constructed without error.
    assert app is not None
