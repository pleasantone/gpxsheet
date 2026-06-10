"""Tests for the public library API: render / analyze / validate."""

from __future__ import annotations

from pathlib import Path

import pytest

import gpxsheet
from gpxsheet.validate import Finding, ValidationReport

PDF_MAGIC = b"%PDF"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("layout", ["portrait", "landscape", "preview", "strip"])
@pytest.mark.parametrize(
    "fmt,magic", [("pdf", PDF_MAGIC), ("png", PNG_MAGIC)]
)
def test_render_layout_format_matrix(l_route_file, tmp_path, layout, fmt, magic):
    out = tmp_path / f"{layout}.{fmt}"
    result = gpxsheet.render(str(l_route_file), str(out), layout=layout, format=fmt)
    assert Path(result) == out
    assert out.read_bytes()[: len(magic)] == magic


def test_render_defaults_portrait_pdf(l_route_file, tmp_path):
    out = tmp_path / "route.pdf"
    gpxsheet.render(str(l_route_file), str(out))  # no layout/format -> portrait pdf
    assert out.read_bytes()[:4] == PDF_MAGIC


def test_render_default_output_name(l_route_file, tmp_path, monkeypatch):
    # output_file=None -> route.<format> in the cwd.
    monkeypatch.chdir(tmp_path)
    result = gpxsheet.render(str(l_route_file), format="png", layout="preview")
    assert result == "route.png"
    assert (tmp_path / "route.png").read_bytes()[:8] == PNG_MAGIC


@pytest.mark.parametrize("dpl", [0, None])
@pytest.mark.parametrize("layout", ["portrait", "landscape", "preview"])
def test_render_auto_fit_decisions_per_lane(l_route_file, tmp_path, layout, dpl):
    # decisions_per_lane=0/None -> auto-fit; must still render a valid PDF.
    out = tmp_path / f"{layout}.pdf"
    gpxsheet.render(str(l_route_file), str(out), layout=layout, decisions_per_lane=dpl)
    assert out.read_bytes()[:4] == PDF_MAGIC


def test_validate_returns_report(l_route_file):
    report = gpxsheet.validate(str(l_route_file), fuel_range=1.0)
    assert isinstance(report, ValidationReport)
    assert report.route is not None
    assert report.length_miles > 0
    assert report.name == report.route.name
    assert all(isinstance(f, Finding) for f in report.findings)
    # A tiny fuel range on a multi-mile route -> at least one warning finding.
    assert any(f.level == "warning" for f in report.findings)


def test_removed_helpers_are_gone():
    # generate_pdf / generate_strip were replaced by render().
    assert not hasattr(gpxsheet, "generate_pdf")
    assert not hasattr(gpxsheet, "generate_strip")
