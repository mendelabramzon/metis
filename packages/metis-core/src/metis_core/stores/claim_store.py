"""``PostgresClaimStore``: claims, entities, events, and the extraction batch.

Writes are idempotent by id (re-writing a batch skips already-present rows), so the
pipeline can re-run without duplicating logical facts.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit.sink import emit_store_audit
from metis_core.db.session import unit_of_work
from metis_core.mappers import (
    claim_to_row,
    entity_to_row,
    event_to_row,
    extraction_batch_to_row,
    to_model,
)
from metis_core.models import ClaimRow, EntityRow, EventRow, ExtractionBatchRow
from metis_protocol import (
    Claim,
    ClaimFilter,
    ClaimId,
    ClaimWriteResult,
    EntityId,
    EventId,
    ExtractionBatch,
)


class PostgresClaimStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write(self, batch: ExtractionBatch) -> ClaimWriteResult:
        written_claims: list[ClaimId] = []
        written_entities: list[EntityId] = []
        written_events: list[EventId] = []
        skipped = 0
        async with unit_of_work(self._sessionmaker) as session:
            for claim in batch.claims:
                if await session.get(ClaimRow, str(claim.id)) is not None:
                    skipped += 1
                    continue
                session.add(claim_to_row(claim))
                written_claims.append(claim.id)
            for entity in batch.entities:
                if await session.get(EntityRow, str(entity.id)) is None:
                    session.add(entity_to_row(entity))
                    written_entities.append(entity.id)
            for event in batch.events:
                if await session.get(EventRow, str(event.id)) is None:
                    session.add(event_to_row(event))
                    written_events.append(event.id)
            if await session.get(ExtractionBatchRow, str(batch.id)) is None:
                session.add(extraction_batch_to_row(batch))
            await emit_store_audit(
                session,
                workspace_id=str(batch.workspace_id),
                action="store.write.extraction_batch",
                target_id=str(batch.id),
                target_kind="ExtractionBatch",
                sensitivity="internal",
            )
        return ClaimWriteResult(
            written_claims=tuple(written_claims),
            written_entities=tuple(written_entities),
            written_events=tuple(written_events),
            skipped=skipped,
        )

    async def query(self, claim_filter: ClaimFilter) -> Sequence[Claim]:
        stmt = select(ClaimRow).where(
            ClaimRow.workspace_id == str(claim_filter.workspace_id),
            ClaimRow.tombstoned_at.is_(None),
        )
        if claim_filter.predicate is not None:
            stmt = stmt.where(ClaimRow.predicate == claim_filter.predicate)
        if claim_filter.text_contains is not None:
            stmt = stmt.where(ClaimRow.body["text"].astext.contains(claim_filter.text_contains))
        if claim_filter.entity is not None:
            entity_id = str(claim_filter.entity.entity_id)
            stmt = stmt.where(
                or_(
                    ClaimRow.body["subject_ref"]["entity_id"].astext == entity_id,
                    ClaimRow.body["object_ref"]["entity_id"].astext == entity_id,
                )
            )
        stmt = stmt.order_by(ClaimRow.created_at.asc())
        if claim_filter.limit is not None:
            stmt = stmt.limit(claim_filter.limit)
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, Claim) for row in rows]

    async def get(self, claim_id: ClaimId) -> Claim | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(ClaimRow, str(claim_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, Claim)
