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


def max_upload_bytes() -> int:
    return int(os.getenv("GPXSHEET_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


def max_points() -> int:
    """Hard cap on track/route points; rejects monster routes before parsing."""
    return int(os.getenv("GPXSHEET_MAX_POINTS", "500000"))


def rate_limit_per_minute() -> int:
    return int(os.getenv("GPXSHEET_RATE_LIMIT_PER_MIN", "60"))


def api_keys() -> frozenset[str]:
    """Accepted API keys (comma-separated). Empty set = auth disabled (dev)."""
    raw = os.getenv("GPXSHEET_API_KEYS", "")
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


def cors_origins() -> list[str]:
    """Allowed CORS origins (comma-separated). Empty = same-origin only."""
    raw = os.getenv("GPXSHEET_CORS_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def trust_first_party() -> bool:
    """When true (and API keys are set), the backend issues a signed, expiring
    first-party token into the served SPA, and accepts it in lieu of an API key.
    Lets the bundled web app work keyless while the raw API stays key-gated.
    Off by default, so self-hosters keep the strict "key required for everyone"
    behavior when they set GPXSHEET_API_KEYS."""
    return os.getenv("GPXSHEET_TRUST_FIRST_PARTY", "").lower() in ("1", "true", "yes")


def session_secret() -> str | None:
    """HMAC secret for signing first-party tokens. Optional: if unset, a random
    per-process secret is used (fine for a single replica; set this to share trust
    across replicas)."""
    return os.getenv("GPXSHEET_SESSION_SECRET") or None


def enable_hsts() -> bool:
    """Send HSTS (only when served over TLS / behind a TLS-terminating proxy)."""
    return os.getenv("GPXSHEET_ENABLE_HSTS", "").lower() in ("1", "true", "yes")


def minio_config() -> dict:
    return {
        "endpoint": os.getenv("GPXSHEET_MINIO_ENDPOINT", "localhost:9000"),
        "access_key": os.getenv("GPXSHEET_MINIO_ACCESS_KEY", "minioadmin"),
        "secret_key": os.getenv("GPXSHEET_MINIO_SECRET_KEY", "minioadmin"),
        "bucket": os.getenv("GPXSHEET_MINIO_BUCKET", "gpxsheet"),
        "secure": os.getenv("GPXSHEET_MINIO_SECURE", "").lower() in ("1", "true", "yes"),
        # Host-reachable endpoint used only to *sign* download URLs (the internal
        # endpoint above isn't reachable outside the docker network).
        "public_endpoint": os.getenv("GPXSHEET_MINIO_PUBLIC_ENDPOINT") or None,
    }

