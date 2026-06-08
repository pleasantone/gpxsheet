"""Request/response models for the web service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateParams(BaseModel):
    """PDF generation parameters (mirrors ``gpxsheet.generate_pdf`` kwargs)."""

    profile: str = "sport-touring"
    fuel_range: float | None = None
    use_osm: bool = True
    turn_style: str = Field("stylized", pattern="^(stylized|faithful)$")
    orientation: str = Field("portrait", pattern="^(portrait|landscape)$")
    lanes_per_page: int = Field(4, ge=1)
    decisions_per_lane: int = Field(4, ge=1)


class JobStatus(BaseModel):
    """Status of a render job."""

    id: str
    status: str  # queued | running | done | error
    error: str | None = None
    result_url: str | None = None
