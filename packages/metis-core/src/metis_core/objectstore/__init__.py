"""Object storage for immutable blobs and generated files."""

from __future__ import annotations

from metis_core.objectstore.base import S3ObjectStore, content_key

__all__ = ["S3ObjectStore", "content_key"]
