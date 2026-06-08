"""End-to-end tests for the CLI command paths via Typer's CliRunner."""

from typer.testing import CliRunner

from gpxsheet import __version__
from gpxsheet.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_analyze_command_runs(l_route_file):
    result = runner.invoke(app, ["analyze", str(l_route_file), "--fuel-range", "2"])
    assert result.exit_code == 0
    assert "Route Length:" in result.stdout
    assert "Decision Points:" in result.stdout
    assert "Road Segments:" in result.stdout
    # The L-route has one fuel waypoint within range warning territory.
    assert "Fuel:" in result.stdout


def test_analyze_minimalist_profile(l_route_file):
    result = runner.invoke(app, ["analyze", str(l_route_file), "--profile", "minimalist"])
    assert result.exit_code == 0
    assert "Fuel:" not in result.stdout
    assert "Reassurance Markers:" not in result.stdout


def test_analyze_rejects_unknown_profile(l_route_file):
    result = runner.invoke(app, ["analyze", str(l_route_file), "--profile", "bogus"])
    assert result.exit_code != 0


def test_analyze_missing_file_errors():
    result = runner.invoke(app, ["analyze", "does-not-exist.gpx"])
    assert result.exit_code != 0


def test_generate_command_writes_pdf(l_route_file, tmp_path):
    out = tmp_path / "g.pdf"
    result = runner.invoke(app, ["generate", str(l_route_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.read_bytes()[:4] == b"%PDF"


def test_validate_command_not_implemented(l_route_file):
    result = runner.invoke(app, ["validate", str(l_route_file)])
    assert result.exit_code != 0
    assert isinstance(result.exception, NotImplementedError)
