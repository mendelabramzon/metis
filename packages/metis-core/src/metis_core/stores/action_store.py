"""``PostgresActionStore``: durable proposed actions — the typed intent the system understood a
free-text request as, persisted before execution, with the human decision recorded.

``propose`` is idempotent by id (a retried interpretation does not duplicate); ``update`` replaces
the row as the action moves proposed -> approved/rejected -> executed/failed; ``list`` is the
approval inbox's workspace-scoped view, newest first, optionally filtered by status.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.mappers import proposed_action_to_row, to_model
from metis_core.models import ProposedActionRow
from metis_protocol import ActionId, ActionStatus, ProposedAction, WorkspaceId


class PostgresActionStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def propose(self, action: ProposedAction) -> ProposedAction:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(ProposedActionRow, str(action.id))
            if existing is not None:
                return to_model(existing, ProposedAction)  # idempotent by id
            session.add(proposed_action_to_row(action))
        return action

    async def get(self, action_id: ActionId) -> ProposedAction | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(ProposedActionRow, str(action_id))
        return to_model(row, ProposedAction) if row is not None else None

    async def list(
        self, workspace_id: WorkspaceId, *, status: ActionStatus | None = None
    ) -> Sequence[ProposedAction]:
        stmt = (
            select(ProposedActionRow)
            .where(ProposedActionRow.workspace_id == str(workspace_id))
            .order_by(ProposedActionRow.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(ProposedActionRow.status == status.value)
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, ProposedAction) for row in rows]

    async def update(self, action: ProposedAction) -> ProposedAction:
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(ProposedActionRow, str(action.id))
            if existing is None:
                session.add(proposed_action_to_row(action))
            else:
                existing.schema_version = action.schema_version
                existing.status = action.status.value
                existing.body = action.model_dump(mode="json")
        return action
