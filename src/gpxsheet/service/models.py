"""Request/response models for the web service.

The worker params (:class:`ReportParams`, :class:`RenderParams`) are the plain,
serializable knobs that travel to the job queue. The ``*Form`` subclasses add the
multipart ``gpx`` upload and are what the POST endpoints bind (so config arrives
as form fields alongside the file, not in the query string).
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import defaults
from ..profiles import VALID_PROFILES


class JobState(StrEnum):
    """Lifecycle states of a job."""

    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class ReportParams(BaseModel):
    """Params for the JSON report endpoints (``/v1/analyze``, ``/v1/validate``)."""

    profile: str = defaults.DEFAULT_PROFILE
    fuel_range: float | None = None

    @field_validator("profile")
    @classmethod
    def _validate_profile(cls, v: str) -> str:
        if v not in VALID_PROFILES:
            valid = ", ".join(sorted(VALID_PROFILES))
            raise ValueError(f"unknown profile {v!r}; choose one of: {valid}")
        return v


class RenderParams(ReportParams):
    """Params for ``/v1/render``.

    ``layout`` and ``format`` pick the shape and the file type; the rest tune it.
    ``preview`` is the whole route as one image and ``strip`` a single schematic
    strip, so ``paper``/``lanes_per_page`` only affect the paginated layouts.
    """

    layout: str = Field("portrait", pattern="^(portrait|landscape|preview|strip)$")
    format: str = Field("pdf", pattern="^(pdf|png)$")
    turn_style: str = Field(defaults.TURN_STYLE, pattern="^(stylized|faithful)$")
    paper: str = Field(defaults.PAPER, pattern="^(letter|a4)$")  # pdf paginated layouts only
    lanes_per_page: int = Field(defaults.LANES_PER_PAGE, ge=1)  # portrait only
    # portrait / landscape / preview / strip; default 0 = auto-fit as many as fit per lane
    decisions_per_lane: int = Field(defaults.DECISIONS_PER_LANE, ge=0)
    # ghosted "roads not taken" stubs at junctions; off by default
    show_branches: bool = defaults.SHOW_BRANCHES


class TableParams(BaseModel):
    """Params for ``/v1/table`` (a GPXtable-backed route table).

    Independent of :class:`ReportParams` — table output skips the analyze/OSM
    pipeline entirely, so none of the profile/fuel knobs apply. ``departure`` is a
    natural-language or ISO time string parsed server-side; ``speed`` of 0 = auto.
    """

    format: str = Field("html", pattern="^(html|markdown)$")
    departure: str | None = None
    speed: float = Field(0.0, ge=0)
    units: str = Field("imperial", pattern="^(imperial|metric)$")
    coordinates: bool = False
    ignore_times: bool = False
    timezone: str | None = None


class ReportForm(ReportParams):
    """Multipart body for the report endpoints: the GPX upload plus the params."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    gpx: UploadFile


class TableForm(TableParams):
    """Multipart body for ``/v1/table``: the GPX upload plus the params."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    gpx: UploadFile


class RenderForm(RenderParams):
    """Multipart body for ``/v1/render``: the GPX upload plus the params."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    gpx: UploadFile


class JobStatus(BaseModel):
    """Status of a job."""

    id: str
    status: JobState
    error: str | None = None
    result_url: str | None = None
    content_type: str | None = None  # of the result artifact, once done
    # Number of still-pending jobs (queued or running) ahead of this one in the
    # worker queue, while this job is itself waiting. None once it starts/finishes,
    # or when the backend can't order the queue (e.g. the Dramatiq/Redis path).
    queue_position: int | None = None
