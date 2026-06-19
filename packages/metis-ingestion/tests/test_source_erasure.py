"""Source-level erasure: artifacts are stamped with their producing source and erased by it.

The pipeline stamps each raw artifact with the registered ``source_id``; ``erase_source`` then
removes exactly that source's artifacts (cascade + blob) — not other sources, even in the same
workspace. Runs against Postgres + MinIO via the pipeline fixtures.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit import PostgresAuditSink
from metis_core.models import RawArtifactRow
from metis_core.objectstore import S3ObjectStore
from metis_core.security.deletion import erase_source, erase_workspace_artifacts
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
)
from metis_ingestion import IngestionPipeline, LocalFolderConnector
from metis_protocol import PolicyState, SourceId, WorkspaceId

WORKSPACE = WorkspaceId(f"ws_{'a' * 32}")
SOURCE_A = SourceId(f"src_{'a' * 32}")
SOURCE_B = SourceId(f"src_{'b' * 32}")


async def _live_artifacts(
    sessionmaker: async_sessionmaker[AsyncSession], source_id: SourceId
) -> int:
    stmt = (
        select(func.count())
        .select_from(RawArtifactRow)
        .where(
            RawArtifactRow.source_id == str(source_id),
            RawArtifactRow.tombstoned_at.is_(None),
        )
    )
    async with sessionmaker() as session:
        return (await session.execute(stmt)).scalar_one()


async def test_artifacts_are_stamped_and_erased_by_source(
    sample_dir: Path,
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: S3ObjectStore,
) -> None:
    pipeline = IngestionPipeline(
        connector=LocalFolderConnector(sample_dir, workspace_id=WORKSPACE, policy=PolicyState()),
        artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
        document_store=PostgresDocumentStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
        source_id=SOURCE_A,
    )
    result = await pipeline.run()
    assert result.artifacts == 8
    assert await _live_artifacts(sessionmaker, SOURCE_A) == 8  # every artifact carries its source

    # Erasing a *different* source removes nothing — enumeration is precise, not connector-wide.
    empty = await erase_source(
        sessionmaker, object_store, workspace_id=str(WORKSPACE), source_id=str(SOURCE_B)
    )
    assert empty.artifacts == 0
    assert await _live_artifacts(sessionmaker, SOURCE_A) == 8

    # Erasing the producing source removes exactly its artifacts (and tombstones derived claims).
    erased = await erase_source(
        sessionmaker, object_store, workspace_id=str(WORKSPACE), source_id=str(SOURCE_A)
    )
    assert erased.artifacts == 8
    assert erased.claims >= 1
    assert await _live_artifacts(sessionmaker, SOURCE_A) == 0


async def test_erase_workspace_artifacts_purges_everything(
    sample_dir: Path,
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: S3ObjectStore,
) -> None:
    """User erasure builds on this: every artifact in the (personal) workspace is removed."""
    pipeline = IngestionPipeline(
        connector=LocalFolderConnector(sample_dir, workspace_id=WORKSPACE, policy=PolicyState()),
        artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
        document_store=PostgresDocumentStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
        source_id=SOURCE_A,
    )
    await pipeline.run()

    erased = await erase_workspace_artifacts(
        sessionmaker, object_store, workspace_id=str(WORKSPACE)
    )
    assert erased.artifacts == 8
    assert await _live_artifacts(sessionmaker, SOURCE_A) == 0
