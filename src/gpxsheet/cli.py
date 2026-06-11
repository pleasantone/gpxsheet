"""Command-line interface for GPXSheet.

Exposes the three output modes from docs/product.md: generate (default), ``analyze``
and ``validate``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import DEFAULT_PROFILE, __version__, defaults

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Convert GPX routes into glanceable motorcycle tank-bag navigation PDFs.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"gpxsheet {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """GPXSheet command-line interface."""


@app.command()
def generate(
    gpx_file: Path = typer.Argument(..., exists=True, readable=True, help="Input GPX file."),
    output: Path = typer.Option("route.pdf", "--output", "-o", help="Output PDF path."),
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="minimalist | sport-touring | rally."
    ),
    fuel_range: float | None = typer.Option(
        None, "--fuel-range", help="Rider fuel range in miles."
    ),
    turns: str = typer.Option(
        defaults.TURN_STYLE, "--turns", help="Bend style at turns: stylized | faithful."
    ),
    branches: bool = typer.Option(
        defaults.SHOW_BRANCHES, "--branches/--no-branches",
        help="Draw ghosted 'roads not taken' stubs at junctions (default off).",
    ),
    landscape: bool = typer.Option(
        False, "--landscape",
        help="One big strip per page instead of the default portrait roadbook.",
    ),
    paper: str = typer.Option(
        defaults.PAPER, "--paper", help="Page size: letter | a4."
    ),
    lanes: int = typer.Option(
        defaults.LANES_PER_PAGE, "--lanes", min=1, help="Portrait only: strip lanes per page."
    ),
    lane_decisions: int = typer.Option(
        defaults.DECISIONS_PER_LANE, "--lane-decisions", min=0,
        help="Max decisions per page (portrait lane / landscape page); default 0 = auto-fit.",
    ),
) -> None:
    """Generate a tank-bag navigation PDF (portrait roadbook)."""
    from . import render

    out = render(
        str(gpx_file),
        str(output),
        profile=profile,
        fuel_range=fuel_range,
        layout="landscape" if landscape else "portrait",
        format="pdf",
        turn_style=turns,
        show_branches=branches,
        paper=paper,
        lanes_per_page=lanes,
        decisions_per_lane=lane_decisions,
    )
    typer.echo(f"Wrote {out}")


@app.command()
def analyze(
    gpx_file: Path = typer.Argument(..., exists=True, readable=True, help="Input GPX file."),
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="minimalist | sport-touring | rally."
    ),
    fuel_range: float | None = typer.Option(
        None, "--fuel-range", help="Rider fuel range in miles."
    ),
    reassurance_interval: float | None = typer.Option(
        None, "--reassurance-interval", help="Miles between reassurance markers."
    ),
) -> None:
    """Produce a text route analysis (decision points, fuel, segments)."""
    from . import analyze as _analyze
    from .report import format_analysis

    route = _analyze(
        str(gpx_file),
        profile=profile,
        fuel_range=fuel_range,
        reassurance_interval=reassurance_interval,
    )
    typer.echo(format_analysis(route))


@app.command()
def strip(
    gpx_file: Path = typer.Argument(..., exists=True, readable=True, help="Input GPX file."),
    output: Path = typer.Option("route_strip.png", "--output", "-o", help="Output PNG path."),
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="minimalist | sport-touring | rally."
    ),
    fuel_range: float | None = typer.Option(
        None, "--fuel-range", help="Rider fuel range in miles."
    ),
    turns: str = typer.Option(
        defaults.TURN_STYLE, "--turns", help="Bend style at turns: stylized | faithful."
    ),
    branches: bool = typer.Option(
        defaults.SHOW_BRANCHES, "--branches/--no-branches",
        help="Draw ghosted 'roads not taken' stubs at junctions (default off).",
    ),
) -> None:
    """Render the schematic map strip to a PNG."""
    from . import render

    out = render(
        str(gpx_file),
        str(output),
        profile=profile,
        fuel_range=fuel_range,
        layout="strip",
        format="png",
        turn_style=turns,
        show_branches=branches,
    )
    typer.echo(f"Wrote {out}")


@app.command()
def preview(
    gpx_file: Path = typer.Argument(..., exists=True, readable=True, help="Input GPX file."),
    output: Path = typer.Option("route_preview.png", "--output", "-o", help="Output image path."),
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="minimalist | sport-touring | rally."
    ),
    fuel_range: float | None = typer.Option(
        None, "--fuel-range", help="Rider fuel range in miles."
    ),
    turns: str = typer.Option(
        defaults.TURN_STYLE, "--turns", help="Bend style at turns: stylized | faithful."
    ),
    branches: bool = typer.Option(
        defaults.SHOW_BRANCHES, "--branches/--no-branches",
        help="Draw ghosted 'roads not taken' stubs at junctions (default off).",
    ),
    lane_decisions: int = typer.Option(
        defaults.DECISIONS_PER_LANE, "--lane-decisions", min=0,
        help="Max decisions per strip lane; default 0 = auto-fit.",
    ),
) -> None:
    """Render the whole route as one non-paginated image (stacked strip lanes).

    An on-screen overview: the entire route as a column of strip blocks, no page
    breaks.
    """
    from . import render

    out = render(
        str(gpx_file),
        str(output),
        profile=profile,
        fuel_range=fuel_range,
        layout="preview",
        format="png",
        turn_style=turns,
        show_branches=branches,
        decisions_per_lane=lane_decisions,
    )
    typer.echo(f"Wrote {out}")


@app.command()
def validate(
    gpx_file: Path = typer.Argument(..., exists=True, readable=True, help="Input GPX file."),
    fuel_range: float | None = typer.Option(
        None, "--fuel-range", help="Rider fuel range in miles."
    ),
) -> None:
    """Validate a route for fuel gaps, unpaved segments and ferry crossings.

    Exits non-zero if any warnings are found.
    """
    from . import validate as _validate
    from .validate import WARNING, format_findings

    report = _validate(str(gpx_file), fuel_range=fuel_range)
    typer.echo(format_findings(report.route, report.findings))
    if any(f.level == WARNING for f in report.findings):
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
