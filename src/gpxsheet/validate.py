"""Route validation (the ``validate`` output mode in PRODUCT.md).

Reports hazards/warnings for a route: fuel gaps exceeding the rider's range,
unpaved stretches, and ferry crossings. Operates on an already-analyzed
:class:`~gpxsheet.models.Route`; the unpaved/ferry checks need OSM data
(`analyze(..., include_hazards=True)`), and degrade to a "skipped" note when OSM
data isn't available (osmnx missing, sparse route, or Overpass failure).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Route

# A route stretch this long on unpaved/track surface is worth warning about.
UNPAVED_WARN_MILES = 0.2

WARNING = "warning"
INFO = "info"


@dataclass(frozen=True, slots=True)
class Finding:
    level: str  # WARNING | INFO
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """An analyzed route plus its validation findings (returned by ``validate``)."""

    route: Route
    findings: list[Finding]

    @property
    def name(self) -> str:
        return self.route.name

    @property
    def length_miles(self) -> float:
        return self.route.length_miles


def validate_route(route: Route, *, fuel_range: float | None = None) -> list[Finding]:
    """Return validation findings for an analyzed route."""
    findings: list[Finding] = []

    # --- Fuel range -------------------------------------------------------
    report = route.fuel_report
    if fuel_range is None:
        findings.append(Finding(INFO, "fuel", "Fuel not checked (no --fuel-range given)."))
    elif report is None:
        findings.append(Finding(INFO, "fuel", "Fuel not analyzed for this profile."))
    elif not report.exceeds_range:
        pass  # within range — a short route needs no fuel stops
    elif not route.fuel_stops:
        findings.append(
            Finding(
                WARNING,
                "fuel",
                f"No fuel stops found; the whole {report.longest_gap_miles:.0f} mi route "
                f"exceeds the {fuel_range:.0f} mi range.",
            )
        )
    else:
        findings.append(
            Finding(
                WARNING,
                "fuel",
                f"Longest fuel gap {report.longest_gap_miles:.0f} mi exceeds the "
                f"{fuel_range:.0f} mi range.",
            )
        )

    # --- Unpaved surface (needs OSM) -------------------------------------
    if route.unpaved_miles is None:
        findings.append(Finding(INFO, "unpaved", "Unpaved check skipped (no OSM data)."))
    elif route.unpaved_miles >= UNPAVED_WARN_MILES:
        findings.append(
            Finding(
                WARNING,
                "unpaved",
                f"Route includes ~{route.unpaved_miles:.1f} mi of unpaved/track surface.",
            )
        )

    # --- Ferry crossings (needs OSM) ------------------------------------
    if route.ferry_crossings is None:
        findings.append(Finding(INFO, "ferry", "Ferry check skipped (no OSM data)."))
    elif route.ferry_crossings:
        names = ", ".join(route.ferry_crossings)
        findings.append(Finding(WARNING, "ferry", f"Ferry crossing present: {names}."))

    # --- Seasonal closure (not yet implemented) -------------------------
    findings.append(
        Finding(INFO, "seasonal", "Seasonal-closure risk is not checked yet (see TODO.md).")
    )

    return findings


def format_findings(route: Route, findings: list[Finding]) -> str:
    """Human-readable validation report."""
    lines = [f"Validate: {route.name}  ({route.length_miles:.1f} mi)", ""]
    warnings = [f for f in findings if f.level == WARNING]
    if warnings:
        lines += [f"⚠ {f.message}" for f in warnings]
    else:
        lines.append("✓ No warnings.")
    notes = [f for f in findings if f.level == INFO]
    if notes:
        lines.append("")
        lines += [f"· {f.message}" for f in notes]
    return "\n".join(lines)
