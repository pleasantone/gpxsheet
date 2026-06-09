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


def test_strip_renders_branches_and_roundabout(tmp_path):
    from gpxsheet.models import (
        Branch,
        DecisionKind,
        DecisionPoint,
        GeoPoint,
        Route,
        Segment,
    )
    from gpxsheet.strip import render_route_strip

    pts = [GeoPoint(0.0, 0.0), GeoPoint(0.0, 0.2)]
    route = Route(
        name="Topo",
        points=pts,
        distances_m=[0.0, 16 * 1609.344],
        segments=[Segment("A Rd", 0, 6), Segment("B Rd", 6, 11), Segment("C Rd", 11, 16)],
        decision_points=[
            DecisionPoint(
                6.0, "Right onto B Rd", 70, 0, 0, turn_angle=80,
                branches=(Branch("left", -85, "Side St"), Branch("straight", 3, "A Rd")),
            ),
            DecisionPoint(
                11.0, "At the roundabout, take the 2nd exit onto C Rd", 60, 0, 0,
                kind=DecisionKind.ROUNDABOUT, roundabout_exit=2,
            ),
        ],
    )
    out = tmp_path / "topo.png"
    render_route_strip(route, out)
    assert out.read_bytes()[:8] == PNG_MAGIC
