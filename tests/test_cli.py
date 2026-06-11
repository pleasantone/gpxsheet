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
    # The offshore L-route returns no OSM data, so enrichment falls back to
    # geometry-only -- offline and deterministic via the committed cache.
    result = runner.invoke(app, ["analyze", str(l_route_file), "--fuel-range", "2"])
    assert result.exit_code == 0
    assert "Route Length:" in result.stdout
    assert "Decision Points:" in result.stdout
    assert "Road Segments:" in result.stdout
    # The L-route has one fuel waypoint within range warning territory.
    assert "Fuel:" in result.stdout


def test_analyze_minimalist_profile(l_route_file):
    result = runner.invoke(
        app, ["analyze", str(l_route_file), "--profile", "minimalist"]
    )
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


def test_generate_no_branches_flag(l_route_file, tmp_path):
    # --no-branches suppresses the roads-not-taken stubs; still a valid PDF.
    out = tmp_path / "nb.pdf"
    result = runner.invoke(app, ["generate", str(l_route_file), "-o", str(out), "--no-branches"])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.read_bytes()[:4] == b"%PDF"


def test_generate_landscape_layout(l_route_file, tmp_path):
    out = tmp_path / "ls.pdf"
    result = runner.invoke(
        app, ["generate", str(l_route_file), "-o", str(out), "--layout", "landscape"]
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:4] == b"%PDF"


def test_generate_strip_layout(l_route_file, tmp_path):
    out = tmp_path / "strip.png"
    result = runner.invoke(
        app, ["generate", str(l_route_file), "-o", str(out), "--layout", "strip"]
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_format_inferred_from_png_extension(l_route_file, tmp_path):
    out = tmp_path / "route.png"
    result = runner.invoke(app, ["generate", str(l_route_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_default_output_for_strip(l_route_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["generate", str(l_route_file), "--layout", "strip"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "route_strip.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_validate_command_ok(l_route_file):
    # No fuel-range; the offshore route yields no OSM data -> no warnings -> exit 0.
    result = runner.invoke(app, ["validate", str(l_route_file)])
    assert result.exit_code == 0, result.output
    assert "Validate:" in result.stdout
    assert "Unpaved check skipped" in result.stdout  # no OSM data for an offshore route


def test_validate_command_warns_on_fuel_gap(l_route_file):
    # Tiny fuel range -> the route exceeds it -> warning -> exit 1.
    result = runner.invoke(app, ["validate", str(l_route_file), "--fuel-range", "1"])
    assert result.exit_code == 1
    assert "⚠" in result.stdout
    assert "fuel gap" in result.stdout.lower() or "range" in result.stdout.lower()
