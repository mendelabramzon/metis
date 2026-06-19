"""Tombstone (soft-delete) propagation across the derived-artifact graph.

Tombstoning a raw artifact cascades to its normalized/parsed docs and segments, to
claims that cite it (via the artifact ids denormalized into each source-span ref),
and to mem cells built on those claims. Rows are marked, not deleted, so the trail
stays auditable; physical erasure of blobs is Stage 14.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, Update, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute

from metis_core._util import now_utc
from metis_core.audit.sink import emit_store_audit
from metis_core.db.session import unit_of_work
from metis_core.models import (
    ClaimRow,
    MemCellRow,
    NormalizedDocRow,
    ParsedDocRow,
    RawArtifactRow,
    SegmentRow,
)


@dataclass(frozen=True)
class TombstoneResult:
    raw_artifacts: int
    normalized_docs: int
    parsed_docs: int
    segments: int
    claims: int
    mem_cells: int


async def _ids(
    session: AsyncSession,
    column: InstrumentedAttribute[str],
    condition: ColumnElement[bool],
) -> list[str]:
    return list((await session.scalars(select(column).where(condition))).all())


async def _tombstone(session: AsyncSession, stmt: Update) -> int:
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount


async def tombstone_artifact(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    workspace_id: str,
    artifact_id: str,
) -> TombstoneResult:
    """Tombstone a raw artifact and everything derived from it. Returns row counts."""
    now: datetime = now_utc()
    async with unit_of_work(sessionmaker) as session:
        # Ownership guard: refuse to cascade when the raw artifact is owned by *another* workspace.
        # The doc/segment updates below key off artifact_id/doc_id (not workspace_id), so without
        # this a caller passing another workspace's artifact id would tombstone its docs/segments —
        # an ACL leak. (A missing raw row is allowed through: the claim/mem-cell cascade is already
        # workspace-scoped, so callers that tombstone derived rows without a raw parent still work.)
        owner = await session.scalar(
            select(RawArtifactRow.workspace_id).where(RawArtifactRow.id == artifact_id)
        )
        if owner is not None and owner != workspace_id:
            return TombstoneResult(0, 0, 0, 0, 0, 0)

        raw = await _tombstone(
            session,
            update(RawArtifactRow)
            .where(RawArtifactRow.id == artifact_id, RawArtifactRow.tombstoned_at.is_(None))
            .values(tombstoned_at=now),
        )

        doc_ids = await _ids(
            session, NormalizedDocRow.id, NormalizedDocRow.artifact_id == artifact_id
        )
        normalized = await _tombstone(
            session,
            update(NormalizedDocRow)
            .where(
                NormalizedDocRow.artifact_id == artifact_id,
                NormalizedDocRow.tombstoned_at.is_(None),
            )
            .values(tombstoned_at=now),
        )

        parsed = 0
        segments = 0
        if doc_ids:
            parsed = await _tombstone(
                session,
                update(ParsedDocRow)
                .where(ParsedDocRow.doc_id.in_(doc_ids), ParsedDocRow.tombstoned_at.is_(None))
                .values(tombstoned_at=now),
            )
            segments = await _tombstone(
                session,
                update(SegmentRow)
                .where(SegmentRow.doc_id.in_(doc_ids), SegmentRow.tombstoned_at.is_(None))
                .values(tombstoned_at=now),
            )

        claim_ids = await _ids(
            session,
            ClaimRow.id,
            and_(
                ClaimRow.workspace_id == workspace_id,
                ClaimRow.body["source_spans"].contains([{"artifact_id": artifact_id}]),
            ),
        )
        claims = 0
        mem_cells = 0
        if claim_ids:
            claims = await _tombstone(
                session,
                update(ClaimRow)
                .where(ClaimRow.id.in_(claim_ids), ClaimRow.tombstoned_at.is_(None))
                .values(tombstoned_at=now),
            )
            cites_tombstoned_claim = or_(
                *(MemCellRow.body["claims"].contains([{"claim_id": cid}]) for cid in claim_ids)
            )
            mem_cells = await _tombstone(
                session,
                update(MemCellRow)
                .where(
                    MemCellRow.workspace_id == workspace_id,
                    cites_tombstoned_claim,
                    MemCellRow.tombstoned_at.is_(None),
                )
                .values(tombstoned_at=now),
            )

        await emit_store_audit(
            session,
            workspace_id=workspace_id,
            action="store.tombstone.raw_artifact",
            target_id=artifact_id,
            target_kind="RawArtifact",
            sensitivity="internal",
        )
    return TombstoneResult(raw, normalized, parsed, segments, claims, mem_cells)
