"""Audit-chain integrity verification."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from metis_core.audit.sink import chain_hash
from metis_core.models import AuditEventRow
from metis_protocol import AuditEvent


@dataclass(frozen=True)
class ChainStatus:
    ok: bool
    checked: int
    broken_at_seq: int | None = None
    reason: str | None = None


async def verify_chain(session: AsyncSession, workspace_id: str) -> ChainStatus:
    """Replay a workspace's audit chain and report the first break, if any."""
    rows = (
        (
            await session.execute(
                select(AuditEventRow)
                .where(AuditEventRow.workspace_id == workspace_id)
                .order_by(AuditEventRow.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    prev_hash: str | None = None
    for index, row in enumerate(rows):
        expected_seq = index + 1
        if row.seq != expected_seq:
            return ChainStatus(False, index, row.seq, "non-contiguous seq")
        event = AuditEvent.model_validate(row.body)
        if row.prev_hash != prev_hash:
            return ChainStatus(False, index, row.seq, "prev_hash mismatch")
        if chain_hash(prev_hash, event, row.seq) != row.audit_hash:
            return ChainStatus(False, index, row.seq, "hash mismatch")
        prev_hash = row.audit_hash
    return ChainStatus(True, len(rows))
