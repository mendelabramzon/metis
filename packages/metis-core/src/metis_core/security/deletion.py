"""Right-to-erasure: tombstone derived artifacts and physically erase raw blobs, per policy.

Builds on the Stage 2 tombstone cascade (raw -> docs -> segments -> claims -> mem cells), then takes
the irreversible step the cascade deferred: deleting the raw artifact's object-store blob.
Tombstones keep the trail auditable; blob erasure satisfies right-to-erasure. Together they remove
or tombstone every tier of the truth hierarchy for an artifact. Blob keys are captured *before* the
cascade so the erasure still works after rows are tombstoned.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.models import RawArtifactRow
from metis_core.tombstone import TombstoneResult, tombstone_artifact
from metis_protocol import ObjectStore


@dataclass(frozen=True)
class ErasureResult:
    tombstoned: TombstoneResult
    blobs_erased: int


async def erase_artifact(
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: ObjectStore,
    *,
    workspace_id: str,
    artifact_id: str,
) -> ErasureResult:
    """Tombstone an artifact's derived graph and erase its raw blob from the object store."""
    async with unit_of_work(sessionmaker) as session:
        keys = list(
            (
                await session.scalars(
                    select(RawArtifactRow.storage_ref).where(
                        RawArtifactRow.id == artifact_id,
                        RawArtifactRow.workspace_id == workspace_id,
                    )
                )
            ).all()
        )

    tombstoned = await tombstone_artifact(
        sessionmaker, workspace_id=workspace_id, artifact_id=artifact_id
    )

    erased = 0
    for key in keys:
        await object_store.delete(key)
        erased += 1
    return ErasureResult(tombstoned=tombstoned, blobs_erased=erased)


@dataclass(frozen=True)
class ErasureSummary:
    """Aggregate of a multi-artifact erasure: how many raw artifacts were erased (each with its
    derived graph tombstoned + blob deleted), and the summed derived-row counts."""

    artifacts: int
    claims: int
    mem_cells: int
    blobs_erased: int


async def _erase_each(
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: ObjectStore,
    *,
    workspace_id: str,
    artifact_ids: Sequence[str],
) -> ErasureSummary:
    """Erase each raw artifact (cascade + blob) and aggregate the counts."""
    artifacts = claims = mem_cells = blobs = 0
    for artifact_id in artifact_ids:
        result = await erase_artifact(
            sessionmaker, object_store, workspace_id=workspace_id, artifact_id=artifact_id
        )
        artifacts += result.tombstoned.raw_artifacts
        claims += result.tombstoned.claims
        mem_cells += result.tombstoned.mem_cells
        blobs += result.blobs_erased
    return ErasureSummary(
        artifacts=artifacts, claims=claims, mem_cells=mem_cells, blobs_erased=blobs
    )


async def erase_source(
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: ObjectStore,
    *,
    workspace_id: str,
    source_id: str,
) -> ErasureSummary:
    """Erase every raw artifact a source produced, within its workspace (cascade + blob each).

    Enumerates by the ``source_id`` stamped on each artifact at ingest, so this removes exactly what
    the source brought in — not other sources sharing the same connector or workspace. Removing the
    source *registration* (config/cursor/runs) is the caller's separate step."""
    async with unit_of_work(sessionmaker) as session:
        artifact_ids = list(
            (
                await session.scalars(
                    select(RawArtifactRow.id).where(
                        RawArtifactRow.workspace_id == workspace_id,
                        RawArtifactRow.source_id == source_id,
                        RawArtifactRow.tombstoned_at.is_(None),
                    )
                )
            ).all()
        )
    return await _erase_each(
        sessionmaker, object_store, workspace_id=workspace_id, artifact_ids=artifact_ids
    )


async def erase_workspace_artifacts(
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: ObjectStore,
    *,
    workspace_id: str,
) -> ErasureSummary:
    """Erase every (non-tombstoned) raw artifact in a workspace — its whole evidence graph. Purges a
    user's personal workspace as part of right-to-erasure."""
    async with unit_of_work(sessionmaker) as session:
        artifact_ids = list(
            (
                await session.scalars(
                    select(RawArtifactRow.id).where(
                        RawArtifactRow.workspace_id == workspace_id,
                        RawArtifactRow.tombstoned_at.is_(None),
                    )
                )
            ).all()
        )
    return await _erase_each(
        sessionmaker, object_store, workspace_id=workspace_id, artifact_ids=artifact_ids
    )
