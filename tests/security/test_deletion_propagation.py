"""Right-to-erasure tombstones derived artifacts and erases the raw blob (Docker-backed)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit import PostgresAuditSink
from metis_core.db.session import unit_of_work
from metis_core.models import ClaimRow, RawArtifactRow
from metis_core.objectstore import S3ObjectStore
from metis_core.security import erase_artifact
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
)
from metis_ingestion import IngestionPipeline, LocalFolderConnector
from metis_protocol import PolicyState, WorkspaceId


async def _live_claims(
    sessionmaker: async_sessionmaker[AsyncSession], workspace: WorkspaceId
) -> list[ClaimRow]:
    async with unit_of_work(sessionmaker) as session:
        return list(
            (
                await session.execute(
                    select(ClaimRow).where(
                        ClaimRow.workspace_id == str(workspace),
                        ClaimRow.tombstoned_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )


async def test_erasure_tombstones_derived_and_deletes_blob(
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: S3ObjectStore,
    workspace: WorkspaceId,
    tmp_path,
) -> None:
    (tmp_path / "memo.txt").write_text(
        "Ada Lovelace is the CTO of Acme. Acme was founded in 2019.", encoding="utf-8"
    )
    pipeline = IngestionPipeline(
        connector=LocalFolderConnector(tmp_path, workspace_id=workspace, policy=PolicyState()),
        artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
        document_store=PostgresDocumentStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
    )
    result = await pipeline.run()
    assert result.artifacts == 1
    assert result.claims >= 1

    async with unit_of_work(sessionmaker) as session:
        row = (
            await session.execute(
                select(RawArtifactRow).where(RawArtifactRow.workspace_id == str(workspace))
            )
        ).scalar_one()
        artifact_id, storage_ref = row.id, row.storage_ref

    assert await _live_claims(sessionmaker, workspace)  # derived evidence exists
    assert await object_store.exists(storage_ref)  # blob is stored

    erasure = await erase_artifact(
        sessionmaker, object_store, workspace_id=str(workspace), artifact_id=artifact_id
    )
    assert erasure.tombstoned.raw_artifacts == 1
    assert erasure.tombstoned.claims >= 1
    assert erasure.blobs_erased == 1

    # derived claims are tombstoned and the raw blob is physically gone
    assert await _live_claims(sessionmaker, workspace) == []
    assert not await object_store.exists(storage_ref)
