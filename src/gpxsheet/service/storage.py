"""Result storage: where rendered PDFs live.

``LocalStorage`` (a directory) for dev/tests; ``MinioStorage`` (S3-compatible)
for the self-hosted deployment. The API streams the bytes when no external URL is
available, or redirects to a presigned URL when there is one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> None: ...

    def load(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def url(self, key: str) -> str | None:
        """A directly fetchable URL, or None if the API should stream the bytes."""
        ...


class LocalStorage:
    """Stores results as files under ``root``; no external URLs (API streams)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self._path(key).write_bytes(data)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def url(self, key: str) -> str | None:
        return None


class MinioStorage:
    """S3-compatible storage (MinIO). Returns presigned GET URLs."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        *,
        secure: bool = False,
        url_expiry_seconds: int = 3600,
    ) -> None:
        from minio import Minio

        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket
        self._expiry = url_expiry_seconds
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        import io

        self._client.put_object(
            self._bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )

    def load(self, key: str) -> bytes:
        resp = self._client.get_object(self._bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.stat_object(self._bucket, key)
            return True
        except S3Error:
            return False

    def url(self, key: str) -> str | None:
        from datetime import timedelta

        return self._client.presigned_get_object(
            self._bucket, key, expires=timedelta(seconds=self._expiry)
        )
