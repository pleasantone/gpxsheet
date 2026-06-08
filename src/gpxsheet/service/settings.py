"""Environment-driven configuration for the web service.

If ``GPXSHEET_REDIS_URL`` is set, the app wires the production path (Redis job
store + Dramatiq queue + MinIO storage). Otherwise it runs a single-process dev
path (in-memory store + local-dir storage + synchronous execution).
"""

from __future__ import annotations

import os


def redis_url() -> str | None:
    return os.getenv("GPXSHEET_REDIS_URL") or None


def results_dir() -> str:
    return os.getenv("GPXSHEET_RESULTS_DIR", "/tmp/gpxsheet-results")


def job_ttl_seconds() -> int:
    return int(os.getenv("GPXSHEET_JOB_TTL", "86400"))


def minio_config() -> dict:
    return {
        "endpoint": os.getenv("GPXSHEET_MINIO_ENDPOINT", "localhost:9000"),
        "access_key": os.getenv("GPXSHEET_MINIO_ACCESS_KEY", "minioadmin"),
        "secret_key": os.getenv("GPXSHEET_MINIO_SECRET_KEY", "minioadmin"),
        "bucket": os.getenv("GPXSHEET_MINIO_BUCKET", "gpxsheet"),
        "secure": os.getenv("GPXSHEET_MINIO_SECURE", "").lower() in ("1", "true", "yes"),
    }
