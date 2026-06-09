"""Request/response models for the web service.

The worker params (:class:`ReportParams`, :class:`RenderParams`) are the plain,
serializable knobs that travel to the job queue. The ``*Form`` subclasses add the
multipart ``gpx`` upload and are what the POST endpoints bind (so config arrives
as form fields alongside the file, not in the query string).
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    """Lifecycle states of a job."""

    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class ReportParams(BaseModel):
    """Params for the JSON report endpoints (``/v1/analyze``, ``/v1/validate``)."""

    profile: str = "sport-touring"
    fuel_range: float | None = None


class RenderParams(ReportParams):
    """Params for ``/v1/render``.

    ``layout`` and ``format`` pick the shape and the file type; the rest tune it.
    ``preview`` is the whole route as one image and ``strip`` a single schematic
    strip, so ``paper``/``lanes_per_page`` only affect the paginated layouts.
    """

    layout: str = Field("portrait", pattern="^(portrait|landscape|preview|strip)$")
    format: str = Field("pdf", pattern="^(pdf|png)$")
    turn_style: str = Field("stylized", pattern="^(stylized|faithful)$")
    paper: str = Field("letter", pattern="^(letter|a4)$")  # pdf paginated layouts only
    lanes_per_page: int = Field(4, ge=1)  # portrait only
    decisions_per_lane: int = Field(4, ge=1)  # portrait / landscape / preview


class ReportForm(ReportParams):
    """Multipart body for the report endpoints: the GPX upload plus the params."""

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
