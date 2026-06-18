"""Right-to-erasure: tombstone derived artifacts and physically erase raw blobs, per policy.

Builds on the Stage 2 tombstone cascade (raw -> docs -> segments -> claims -> mem cells), then takes
the irreversible step the cascade deferred: deleting the raw artifact's object-store blob.
Tombstones keep the trail auditable; blob erasure satisfies right-to-erasure. Together they remove
or tombstone every tier of the truth hierarchy for an artifact. Blob keys are captured *before* the
cascade so the erasure still works after rows are tombstoned.
"""

from __future__ import annotations

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
