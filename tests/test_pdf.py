"""Smoke tests for PDF generation (produces a real multi-page PDF)."""

from pathlib import Path

from typer.testing import CliRunner

from gpxsheet.cli import app

runner = CliRunner()

PDF_MAGIC = b"%PDF"


def test_generate_pdf_writes_valid_pdf(l_route_file, tmp_path):
    import gpxsheet

    out = tmp_path / "route.pdf"
    result = gpxsheet.generate_pdf(str(l_route_file), str(out), profile="sport-touring")
    assert Path(result) == out
    assert out.exists() and out.stat().st_size > 0
    assert out.read_bytes()[:4] == PDF_MAGIC


def test_render_pdf_multipage(tmp_path):
    from gpxsheet.models import DecisionPoint, GeoPoint, Route, Segment
    from gpxsheet.pdf import render_pdf

    decisions = [DecisionPoint(m, f"Turn {m}", 60, 0, 0, turn_angle=45) for m in (40, 80, 120, 160)]
    route = Route(
        name="Multi",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, 200 * 1609.344],
        decision_points=decisions,
        segments=[Segment("Road", 0, 200)],
    )
    out = tmp_path / "multi.pdf"
    render_pdf(route, out)
    data = out.read_bytes()
    assert data[:4] == PDF_MAGIC
    # PdfPages writes one "/Type /Page" per page (plus one "/Type /Pages" tree).
    assert data.count(b"/Type /Page") >= 2


def test_generate_cli_command(l_route_file, tmp_path):
    out = tmp_path / "cli.pdf"
    result = runner.invoke(app, ["generate", str(l_route_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.read_bytes()[:4] == PDF_MAGIC
