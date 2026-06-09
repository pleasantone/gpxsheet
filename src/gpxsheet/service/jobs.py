"""Render jobs: status tracking, the render pipeline, and the task runners.

A render is slow (matplotlib + live OSM), so it runs off the request path. Two
runners share one pipeline (:func:`process_job`):

* ``EagerRunner`` — runs the render inline; used for the single-process dev path
  and tests (no Redis/MinIO needed).
* ``DramatiqRunner`` — enqueues the render onto Dramatiq/Redis for the worker.

Job state lives in a ``JobStore`` (in-memory for dev/tests, Redis for prod).
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol

import dramatiq

from . import settings
from .models import RenderParams, ReportParams
from .render import run_job
from .storage import Storage

# Each endpoint sets an internal op so the worker can rebuild the right params
# model from the serialized dict (op is not part of the client-facing API).
_PARAMS_BY_OP = {"render": RenderParams, "analyze": ReportParams, "validate": ReportParams}

log = logging.getLogger(__name__)

# --- broker (StubBroker unless a Redis URL is configured) -------------------
_redis_url = settings.redis_url()
if _redis_url:
    from dramatiq.brokers.redis import RedisBroker

    dramatiq.set_broker(RedisBroker(url=_redis_url))
else:
    from dramatiq.brokers.stub import StubBroker

    dramatiq.set_broker(StubBroker())


# A render holds the worker for the whole job; big OSM routes can take minutes,
# so cap a single render generously rather than letting it run unbounded.
RENDER_TIME_LIMIT_MS = 1_200_000  # 20 minutes (Dramatiq time_limit is in ms)


@dataclass
class JobRecord:
    id: str
    status: str = "queued"  # queued | running | done | error
    error: str | None = None
    result_key: str | None = None
    content_type: str | None = None  # of the stored artifact (pdf/png/json)
    download_name: str | None = None  # human-friendly filename for downloads
    owner: str | None = None  # identity that created the job (object-level authz)


class JobStore(Protocol):
    def create(self, cache_key: str | None = None, owner: str | None = None) -> str: ...
    def get(self, job_id: str) -> JobRecord | None: ...
    def update(self, job_id: str, **fields) -> None: ...
    def get_cached(self, cache_key: str) -> JobRecord | None: ...
    def ready(self) -> bool: ...


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._by_key: dict[str, str] = {}

    def create(self, cache_key: str | None = None, owner: str | None = None) -> str:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = JobRecord(id=job_id, owner=owner)
        if cache_key:
            self._by_key[cache_key] = job_id
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        rec = self._jobs.get(job_id)
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)

    def get_cached(self, cache_key: str) -> JobRecord | None:
        rec = self._jobs.get(self._by_key.get(cache_key, ""))
        return rec if rec and rec.status == "done" else None

    def ready(self) -> bool:
        return True


class RedisJobStore:
    """Job records as JSON in Redis, keyed ``gpxsheet:job:<id>`` with a TTL."""

    def __init__(self, url: str, ttl_seconds: int | None = None) -> None:
        import redis

        self._r = redis.Redis.from_url(url)
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.job_ttl_seconds()

    def _key(self, job_id: str) -> str:
        return f"gpxsheet:job:{job_id}"

    def _put(self, rec: JobRecord) -> None:
        self._r.set(self._key(rec.id), json.dumps(asdict(rec)), ex=self._ttl)

    def create(self, cache_key: str | None = None, owner: str | None = None) -> str:
        job_id = uuid.uuid4().hex
        self._put(JobRecord(id=job_id, owner=owner))
        if cache_key:
            self._r.set(f"gpxsheet:cache:{cache_key}", job_id, ex=self._ttl)
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        raw = self._r.get(self._key(job_id))
        return JobRecord(**json.loads(raw)) if raw else None

    def update(self, job_id: str, **fields) -> None:
        rec = self.get(job_id)
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)
            self._put(rec)

    def get_cached(self, cache_key: str) -> JobRecord | None:
        job_id = self._r.get(f"gpxsheet:cache:{cache_key}")
        if not job_id:
            return None
        rec = self.get(job_id.decode() if isinstance(job_id, bytes) else job_id)
        return rec if rec and rec.status == "done" else None

    def ready(self) -> bool:
        try:
            return bool(self._r.ping())
        except Exception:  # noqa: BLE001 - any connectivity failure -> not ready
            return False


def process_job(
    store: JobStore, storage: Storage, job_id: str, op: str, gpx_bytes: bytes, params: ReportParams
) -> None:
    """Run the job, store its artifact, and record the outcome on the job."""
    store.update(job_id, status="running")
    try:
        data, content_type, ext, download_name = run_job(op, gpx_bytes, params)
        key = f"{job_id}.{ext}"
        storage.save(key, data, content_type=content_type)
        store.update(
            job_id,
            status="done",
            result_key=key,
            content_type=content_type,
            download_name=download_name,
        )
    except ValueError as exc:
        # Input problems (bad/empty GPX, rejected DTD) are safe to echo back.
        store.update(job_id, status="error", error=str(exc))
    except Exception:  # surface as a failed job, not a crashed worker
        # Don't leak internals (paths, Overpass URLs, stack frames) to clients.
        log.exception("render job %s failed", job_id)
        store.update(job_id, status="error", error="internal render error")


class TaskRunner(Protocol):
    def submit(self, job_id: str, op: str, gpx_bytes: bytes, params: ReportParams) -> None: ...


class EagerRunner:
    """Runs the render synchronously in-process (dev/tests)."""

    def __init__(self, store: JobStore, storage: Storage) -> None:
        self._store = store
        self._storage = storage

    def submit(self, job_id: str, op: str, gpx_bytes: bytes, params: ReportParams) -> None:
        process_job(self._store, self._storage, job_id, op, gpx_bytes, params)


class DramatiqRunner:
    """Enqueues the render onto Dramatiq/Redis for a worker to pick up."""

    def submit(self, job_id: str, op: str, gpx_bytes: bytes, params: ReportParams) -> None:
        render_actor.send(job_id, op, base64.b64encode(gpx_bytes).decode(), params.model_dump())


def prod_components() -> tuple[RedisJobStore, Storage]:
    """Build the Redis store + MinIO storage shared by the API and the worker."""
    from .storage import MinioStorage

    return RedisJobStore(settings.redis_url()), MinioStorage(**settings.minio_config())


@dramatiq.actor(max_retries=0, time_limit=RENDER_TIME_LIMIT_MS)
def render_actor(job_id: str, op: str, gpx_b64: str, params_dict: dict) -> None:
    store, storage = prod_components()
    params = _PARAMS_BY_OP[op](**params_dict)
    process_job(store, storage, job_id, op, base64.b64decode(gpx_b64), params)
