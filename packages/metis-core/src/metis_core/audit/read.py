"""Reading the audit log — the operator-surface query over the append-only events.

The sink only appends (hash-chained); this is the read side an operator UI/API needs: the most
recent events for a workspace, newest first, optionally filtered by action.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.models import AuditEventRow
from metis_protocol import AuditEvent


async def recent_audit_events(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    workspace_id: str,
    action: str | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """The most recent audit events for a workspace (optionally by action), newest first."""
    stmt = select(AuditEventRow).where(AuditEventRow.workspace_id == workspace_id)
    if action is not None:
        stmt = stmt.where(AuditEventRow.body["action"].astext == action)
    stmt = stmt.order_by(AuditEventRow.seq.desc()).limit(limit)
    async with unit_of_work(sessionmaker) as session:
        rows = (await session.scalars(stmt)).all()
    return [AuditEvent.model_validate(row.body) for row in rows]
