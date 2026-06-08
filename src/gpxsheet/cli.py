"""Command-line interface for GPXSheet.

Exposes the three output modes from PRODUCT.md: generate (default), ``analyze``
and ``validate``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import DEFAULT_PROFILE, __version__

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
    osm: bool = typer.Option(
        True, "--osm/--no-osm",
        help="OpenStreetMap road names/fuel (default on; falls back to geometry-only).",
    ),
    turns: str = typer.Option(
        "stylized", "--turns", help="Bend style at turns: stylized | faithful."
    ),
    landscape: bool = typer.Option(
        False, "--landscape",
        help="One big strip per page instead of the default portrait roadbook.",
    ),
    lanes: int = typer.Option(
        4, "--lanes", min=1, help="Portrait only: strip lanes per page."
    ),
    lane_decisions: int = typer.Option(
        4, "--lane-decisions", min=1, help="Portrait only: max decisions per lane."
    ),
) -> None:
    """Generate a tank-bag navigation PDF (portrait roadbook + OSM by default)."""
    from . import generate_pdf

    out = generate_pdf(
        str(gpx_file),
        str(output),
        profile=profile,
        fuel_range=fuel_range,
        use_osm=osm,
        turn_style=turns,
        orientation="landscape" if landscape else "portrait",
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
    osm: bool = typer.Option(
        True, "--osm/--no-osm",
        help="OpenStreetMap road names/fuel (default on; falls back to geometry-only).",
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
        use_osm=osm,
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
    osm: bool = typer.Option(
        True, "--osm/--no-osm",
        help="OpenStreetMap road names/fuel (default on; falls back to geometry-only).",
    ),
    turns: str = typer.Option(
        "stylized", "--turns", help="Bend style at turns: stylized | faithful."
    ),
) -> None:
    """Render the schematic map strip (Milestone 2) to a PNG."""
    from .strip import generate_strip

    out = generate_strip(
        str(gpx_file),
        str(output),
        profile=profile,
        fuel_range=fuel_range,
        use_osm=osm,
        turn_style=turns,
    )
    typer.echo(f"Wrote {out}")


@app.command()
def validate(
    gpx_file: Path = typer.Argument(..., exists=True, readable=True, help="Input GPX file."),
    fuel_range: float | None = typer.Option(
        None, "--fuel-range", help="Rider fuel range in miles."
    ),
) -> None:
    """Validate a route for fuel gaps, unpaved segments and other hazards."""
    raise NotImplementedError("Route validation is not implemented yet (see PRODUCT.md).")


if __name__ == "__main__":  # pragma: no cover
    app()
