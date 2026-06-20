"""PostgresActionStore: propose (idempotent by id), get, list (workspace-scoped + status-filtered),
and update (the proposed -> approved -> executed transition with the decision recorded)."""

from __future__ import annotations

from datetime import UTC, datetime

from metis_core.stores import PostgresActionStore
from metis_protocol import (
    ActionId,
    ActionKind,
    ActionRisk,
    ActionStatus,
    ProposedAction,
    Sensitivity,
    WorkspaceId,
    new_id,
)

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _action(
    workspace_id: WorkspaceId,
    *,
    risk: ActionRisk = ActionRisk.READ_ONLY,
    status: ActionStatus = ActionStatus.PROPOSED,
) -> ProposedAction:
    return ProposedAction(
        id=new_id(ActionId),
        workspace_id=workspace_id,
        kind=ActionKind.ANSWER,
        risk=risk,
        command="what did we ship?",
        summary="Answer: what did we ship?",
        sensitivity=Sensitivity.INTERNAL,
        audit_target="query",
        status=status,
        created_at=_T,
    )


async def test_propose_is_idempotent_by_id(sessionmaker):
    store = PostgresActionStore(sessionmaker)
    action = _action(new_id(WorkspaceId))

    await store.propose(action)
    again = await store.propose(action.model_copy(update={"summary": "changed"}))

    assert again.summary == "Answer: what did we ship?"  # the existing row wins
    fetched = await store.get(action.id)
    assert fetched is not None
    assert fetched.summary == "Answer: what did we ship?"


async def test_list_is_workspace_scoped_and_status_filtered(sessionmaker):
    store = PostgresActionStore(sessionmaker)
    ws = new_id(WorkspaceId)
    mine = await store.propose(_action(ws, risk=ActionRisk.MEMORY_WRITE))
    await store.propose(_action(new_id(WorkspaceId)))  # another workspace

    assert [a.id for a in await store.list(ws)] == [mine.id]  # only this workspace
    assert await store.list(ws, status=ActionStatus.APPROVED) == []  # none approved yet


async def test_update_records_the_decision_and_execution(sessionmaker):
    store = PostgresActionStore(sessionmaker)
    ws = new_id(WorkspaceId)
    action = await store.propose(_action(ws, risk=ActionRisk.MEMORY_WRITE))

    approved = action.model_copy(
        update={"status": ActionStatus.APPROVED, "decided_by": "ada", "decided_at": _T}
    )
    await store.update(approved)
    assert (await store.list(ws, status=ActionStatus.APPROVED))[0].decided_by == "ada"

    await store.update(approved.model_copy(update={"status": ActionStatus.EXECUTED}))
    executed = await store.get(action.id)
    assert executed is not None
    assert executed.status is ActionStatus.EXECUTED
