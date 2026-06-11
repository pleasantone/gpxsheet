"""Smoke tests for the schematic strip renderer (produces a real PNG)."""

from pathlib import Path

from typer.testing import CliRunner

from gpxsheet.cli import app

runner = CliRunner()

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_marker_labels_carry_mileage_and_glyph():
    from types import SimpleNamespace

    from gpxsheet.strip import _kind_glyph, _marker_label

    fuel = _marker_label(SimpleNamespace(kind="fuel", mile=12.3, label="Shell"))
    assert "Fuel: Shell" in fuel and "(12.3 mi)" in fuel
    food = _marker_label(SimpleNamespace(kind="food", mile=8.0, label="Joe's Diner"))
    assert "Joe's Diner" in food and "(8.0 mi)" in food
    wp = _marker_label(SimpleNamespace(kind="waypoint", mile=5.5, label="Vista"))
    assert wp == "Vista  (5.5 mi)"
    # Glyph prefixes are either empty or a single symbol + space; never a tofu box.
    for kind in ("fuel", "food", "ferry"):
        g = _kind_glyph(kind)
        assert g == "" or (len(g) == 2 and g.endswith(" "))


def test_use_bundled_fonts_pins_reproducible_chain():
    # Rendering must depend only on bundled fonts, never on whatever the machine
    # happens to have installed, so output is identical everywhere.
    from matplotlib import rcParams

    from gpxsheet.strip import _font_covers, _kind_glyph, _use_bundled_fonts

    _use_bundled_fonts()
    # Explicit family list (DejaVu Sans for text, Noto Emoji subset as a per-glyph
    # symbol fallback) -- not the generic "sans-serif" alias, which would collapse
    # to one font and break the fallback.
    assert rcParams["font.family"] == ["DejaVu Sans", "Noto Emoji"]

    # The vendored Noto Emoji subset supplies the three symbols DejaVu lacks, so
    # the preferred glyphs are all covered and selected deterministically.
    assert _font_covers(0x26FD) and _font_covers(0x26F4) and _font_covers(0x1F374)
    assert _kind_glyph("fuel") == "⛽ "
    assert _kind_glyph("food") == "🍴 "
    assert _kind_glyph("ferry") == "⛴ "


def test_marker_glyphs_render_without_tofu(tmp_path):
    # The fuel/ferry/food glyphs must actually rasterize (no "missing glyph"
    # warning) and the Noto subset must embed in the PDF.
    import warnings

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from gpxsheet.layout import PlacedMarker, StripLayout
    from gpxsheet.strip import draw_strip

    markers = [
        PlacedMarker(x=1.0, y=0.0, mile=1.0, kind="fuel", label="Shell"),
        PlacedMarker(x=5.0, y=0.0, mile=5.0, kind="food", label="Diner"),
        PlacedMarker(x=9.0, y=0.0, mile=9.0, kind="ferry", label="Ferry"),
    ]
    layout = StripLayout(
        path=[(0, 0), (5, 0), (10, 0)], markers=markers, ribbon=[], width=10.0, height=1.0
    )
    fig, ax = plt.subplots()
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # missing-glyph warning -> failure
        draw_strip(fig, ax, layout)
        fig.canvas.draw()
    out = tmp_path / "glyphs.pdf"
    fig.savefig(out)
    plt.close(fig)
    assert b"Noto" in out.read_bytes()  # the symbol subset is embedded


def test_render_strip_writes_valid_png(l_route_file, tmp_path):
    import gpxsheet

    out = tmp_path / "strip.png"
    result = gpxsheet.render(
        str(l_route_file), str(out), layout="strip", format="png", profile="sport-touring"
    )
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


def _branch_stub_count(layout, *, show_branches):
    """Number of ghosted branch-stub lines draw_strip emits for ``layout``."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from gpxsheet import colors
    from gpxsheet.strip import draw_strip

    fig, ax = plt.subplots()
    draw_strip(fig, ax, layout, show_branches=show_branches)
    stub = colors.BRANCH_STUB
    n = sum(line.get_color() == stub for line in ax.get_lines())
    plt.close(fig)
    return n


def test_show_branches_toggles_stub_drawing():
    from gpxsheet.layout import PlacedMarker, StripLayout
    from gpxsheet.models import Branch

    marker = PlacedMarker(
        x=5.0, y=0.0, mile=5.0, kind="decision", label="Right onto B Rd",
        branches=(Branch("left", -85, "Side St"),),
    )
    layout = StripLayout(
        path=[(0, 0), (5, 0), (10, 0)], markers=[marker], ribbon=[], width=10.0, height=1.0
    )
    # On by default; the toggle suppresses the ghosted stub line entirely.
    assert _branch_stub_count(layout, show_branches=True) == 1
    assert _branch_stub_count(layout, show_branches=False) == 0
