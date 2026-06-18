"""Content-addressed, write-once object storage over any S3-compatible store.

Implements the protocol ``ObjectStore``. Keys are derived from the sha256 of the
content, so a key is immutable by construction: re-putting the same bytes is a
no-op, and different bytes never collide on a key. boto3 is synchronous, so calls
run in a thread to keep the interface async (ADR 0008).
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def content_key(data: bytes) -> str:
    """A content-addressed object key: ``sha256/<aa>/<full-digest>`` (sharded)."""
    digest = hashlib.sha256(data).hexdigest()
    return f"sha256/{digest[:2]}/{digest}"


class S3ObjectStore:
    """An ``ObjectStore`` backed by AWS S3 or MinIO (path-style addressing)."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._bucket = bucket
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except ClientError:
                self._client.create_bucket(Bucket=self._bucket)

        await asyncio.to_thread(_ensure)

    async def put_bytes(self, key: str, data: bytes) -> str:
        if await self.exists(key):  # content-addressed keys are immutable: write once
            return key
        await asyncio.to_thread(
            lambda: self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        )
        return key

    async def get_bytes(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
            except ClientError:
                return None
            return response["Body"].read()

        return await asyncio.to_thread(_get)

    async def exists(self, key: str) -> bool:
        def _head() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError:
                return False
            return True

        return await asyncio.to_thread(_head)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(lambda: self._client.delete_object(Bucket=self._bucket, Key=key))
