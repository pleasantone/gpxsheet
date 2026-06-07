"""Smoke tests for the schematic strip renderer (produces a real PNG)."""

from pathlib import Path

from typer.testing import CliRunner

from gpxsheet.cli import app

runner = CliRunner()

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_generate_strip_writes_valid_png(l_route_file, tmp_path):
    from gpxsheet.strip import generate_strip

    out = tmp_path / "strip.png"
    result = generate_strip(str(l_route_file), str(out), profile="sport-touring")
    assert Path(result) == out
    assert out.exists() and out.stat().st_size > 0
    assert out.read_bytes()[:8] == PNG_MAGIC  # valid PNG header


def test_strip_cli_command(l_route_file, tmp_path):
    out = tmp_path / "cli_strip.png"
    result = runner.invoke(app, ["strip", str(l_route_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.read_bytes()[:8] == PNG_MAGIC
