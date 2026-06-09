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


def test_portrait_pdf_multilane(tmp_path):
    from gpxsheet.models import DecisionPoint, GeoPoint, Route, Segment
    from gpxsheet.pdf import render_pdf

    # 20 decisions -> 5 lanes (4/lane) -> 2 portrait pages (4 lanes/page).
    decisions = [
        DecisionPoint(m, f"Turn {m}", 60, 0, 0, turn_angle=45) for m in range(10, 210, 10)
    ]
    route = Route(
        name="Portrait",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, 210 * 1609.344],
        decision_points=decisions,
        segments=[Segment("Road", 0, 210)],
    )
    out = tmp_path / "portrait.pdf"
    render_pdf(route, out, orientation="portrait")
    data = out.read_bytes()
    assert data[:4] == PDF_MAGIC
    assert data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 2


def test_invalid_orientation_raises(tmp_path):
    import pytest

    from gpxsheet.models import GeoPoint, Route
    from gpxsheet.pdf import render_pdf

    route = Route(name="x", points=[GeoPoint(0, 0), GeoPoint(0, 1)], distances_m=[0.0, 1609.344])
    with pytest.raises(ValueError, match="orientation"):
        render_pdf(route, tmp_path / "x.pdf", orientation="diagonal")


def test_invalid_paper_raises(tmp_path):
    import pytest

    from gpxsheet.models import GeoPoint, Route
    from gpxsheet.pdf import render_pdf

    route = Route(name="x", points=[GeoPoint(0, 0), GeoPoint(0, 1)], distances_m=[0.0, 1609.344])
    with pytest.raises(ValueError, match="paper"):
        render_pdf(route, tmp_path / "x.pdf", paper="foolscap")


def _mediabox(data: bytes) -> list[float]:
    import re

    m = re.search(rb"/MediaBox \[([\d. ]+)\]", data)
    assert m, "no MediaBox in PDF"
    return [float(x) for x in m.group(1).split()]


def test_a4_page_size(tmp_path):
    from gpxsheet.models import GeoPoint, Route, Segment
    from gpxsheet.pdf import render_pdf

    route = Route(
        name="A4",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, 50 * 1609.344],
        segments=[Segment("Road", 0, 50)],
    )
    # A4 landscape MediaBox is 11.69 x 8.27 in = ~841.7 x 595.4 pt (72 pt/in).
    box = _mediabox((render_pdf(route, tmp_path / "a4.pdf", paper="a4")).read_bytes())
    assert round(box[2]) in (841, 842)
    assert round(box[3]) == 595
    # Letter landscape is 11 x 8.5 in = 792 x 612 pt -- distinct from A4.
    lbox = _mediabox((render_pdf(route, tmp_path / "ltr.pdf", paper="letter")).read_bytes())
    assert round(lbox[2]) == 792
    assert round(lbox[3]) == 612


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int]:
    import struct

    # PNG IHDR: width/height are big-endian uint32 at byte offsets 16 and 20.
    return struct.unpack(">II", data[16:24])


def _preview_route(n_decisions: int):
    from gpxsheet.models import DecisionPoint, GeoPoint, Route, Segment

    miles = list(range(10, 10 * (n_decisions + 1), 10))
    decisions = [DecisionPoint(m, f"Turn {m}", 60, 0, 0, turn_angle=45) for m in miles]
    end = miles[-1] + 10
    return Route(
        name="Preview",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, end * 1609.344],
        decision_points=decisions,
        segments=[Segment("Road", 0, end)],
    )


def test_render_preview_is_single_growing_image(tmp_path):
    from gpxsheet.pdf import render_preview

    # One image (PNG), no pagination -- a longer route just makes a taller image.
    short = render_preview(_preview_route(3), tmp_path / "short.png").read_bytes()
    long = render_preview(_preview_route(20), tmp_path / "long.png").read_bytes()
    assert short[:8] == PNG_MAGIC and long[:8] == PNG_MAGIC
    sw, sh = _png_size(short)
    lw, lh = _png_size(long)
    assert lw == sw  # same width
    assert lh > sh  # more lanes stacked -> taller


def test_preview_cli_command(l_route_file, tmp_path):
    out = tmp_path / "cli_preview.png"
    result = runner.invoke(app, ["preview", str(l_route_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:8] == PNG_MAGIC


def test_generate_cli_command(l_route_file, tmp_path):
    out = tmp_path / "cli.pdf"
    result = runner.invoke(app, ["generate", str(l_route_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.read_bytes()[:4] == PDF_MAGIC
