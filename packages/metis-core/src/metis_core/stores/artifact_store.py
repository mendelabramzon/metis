"""``PostgresMinioArtifactStore``: artifact metadata in Postgres, blobs in the object store.

Raw artifacts are immutable and deduplicated by ``(workspace_id, content_hash)`` — a
second put of the same content returns the existing reference and never overwrites.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit.sink import emit_store_audit
from metis_core.db.session import unit_of_work
from metis_core.mappers import raw_artifact_to_row, to_model
from metis_core.models import RawArtifactRow
from metis_core.objectstore import content_key
from metis_protocol import ArtifactId, ArtifactRef, ObjectStore, RawArtifact


class PostgresMinioArtifactStore:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        object_store: ObjectStore,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._objects = object_store

    async def put(self, raw: RawArtifact) -> ArtifactRef:
        workspace_id = str(raw.provenance.workspace_id)
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.scalar(
                select(RawArtifactRow.id).where(
                    RawArtifactRow.workspace_id == workspace_id,
                    RawArtifactRow.content_hash == raw.content_hash,
                )
            )
            if existing is not None:
                return ArtifactRef(artifact_id=ArtifactId(existing))
            session.add(raw_artifact_to_row(raw))
            await emit_store_audit(
                session,
                workspace_id=workspace_id,
                action="store.write.raw_artifact",
                target_id=str(raw.id),
                target_kind="RawArtifact",
                sensitivity=raw.policy.sensitivity.value,
            )
        return ArtifactRef(artifact_id=raw.id)

    async def get(self, ref: ArtifactRef) -> RawArtifact | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(RawArtifactRow, str(ref.artifact_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, RawArtifact)

    # Beyond the protocol: blob coordination used by ingestion (Stage 3).
    async def put_blob(self, data: bytes) -> str:
        """Store bytes content-addressed; returns the storage ref (object key)."""
        return await self._objects.put_bytes(content_key(data), data)

    async def get_blob(self, raw: RawArtifact) -> bytes | None:
        return await self._objects.get_bytes(raw.storage_ref)
