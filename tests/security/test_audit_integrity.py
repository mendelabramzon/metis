"""The audit hash-chain verifies intact; tampering with any row is detected (Docker-backed)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit import PostgresAuditSink
from metis_core.db.session import unit_of_work
from metis_core.models import AuditEventRow
from metis_core.security import AuditTamperError, assert_intact
from metis_protocol import AgentKind, Attribution, AuditEvent, AuditId, WorkspaceId, new_id


def _event(workspace: WorkspaceId, action: str) -> AuditEvent:
    return AuditEvent(
        id=new_id(AuditId),
        workspace_id=workspace,
        occurred_at=datetime.now(UTC),
        actor=Attribution(agent_kind=AgentKind.SYSTEM, agent="test"),
        action=action,
    )


async def _emit_chain(
    sessionmaker: async_sessionmaker[AsyncSession], workspace: WorkspaceId
) -> None:
    sink = PostgresAuditSink(sessionmaker)
    for action in ("model.call", "skill.run", "store.write"):
        await sink.emit(_event(workspace, action))


async def test_intact_chain_verifies(
    sessionmaker: async_sessionmaker[AsyncSession], workspace: WorkspaceId
) -> None:
    await _emit_chain(sessionmaker, workspace)
    async with unit_of_work(sessionmaker) as session:
        status = await assert_intact(session, str(workspace))
    assert status.ok
    assert status.checked == 3


async def test_tampered_row_is_detected(
    sessionmaker: async_sessionmaker[AsyncSession], workspace: WorkspaceId
) -> None:
    await _emit_chain(sessionmaker, workspace)

    # tamper: rewrite the body of the second event so it no longer matches its stored hash
    async with unit_of_work(sessionmaker) as session:
        row = (
            await session.execute(
                select(AuditEventRow).where(
                    AuditEventRow.workspace_id == str(workspace), AuditEventRow.seq == 2
                )
            )
        ).scalar_one()
        tampered = dict(row.body)
        tampered["action"] = "covertly.changed"
        await session.execute(
            update(AuditEventRow).where(AuditEventRow.id == row.id).values(body=tampered)
        )

    async with unit_of_work(sessionmaker) as session:
        with pytest.raises(AuditTamperError):
            await assert_intact(session, str(workspace))
