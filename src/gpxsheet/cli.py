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
    reassurance_interval: float = typer.Option(
        15.0, "--reassurance-interval", help="Miles between reassurance markers."
    ),
) -> None:
    """Generate a tank-bag navigation PDF (default mode)."""
    from . import generate_pdf

    generate_pdf(
        str(gpx_file),
        str(output),
        profile=profile,
        fuel_range=fuel_range,
        reassurance_interval=reassurance_interval,
    )


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
        False, "--osm", help="Enrich with OpenStreetMap road names/fuel (needs the osm extra)."
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
