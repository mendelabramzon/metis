"""PostgresApprovalQueue: a held skill approval survives in Postgres (submit/pending/approve)."""

from __future__ import annotations

from metis_gateway.backend import PostgresApprovalQueue
from metis_protocol import ContextBundleId, SkillInput, WorkspaceId, new_id

_WS = WorkspaceId("ws_" + "a" * 32)


def _input() -> SkillInput:
    return SkillInput(
        skill_name="notify",
        skill_version="1.0.0",
        arguments={"message": "hi"},
        context_bundle_id=new_id(ContextBundleId),
    )


async def test_submit_pending_then_approve(pg_sessionmaker) -> None:
    queue = PostgresApprovalQueue(pg_sessionmaker, _WS)
    skill_input = _input()

    request = await queue.submit(skill_input)
    assert not await queue.is_approved(skill_input)
    assert [r.key for r in await queue.pending()] == [request.key]

    # Re-submitting the same unit of work is idempotent (no second pending entry).
    await queue.submit(skill_input)
    assert len(await queue.pending()) == 1

    await queue.approve(request.key)
    assert await queue.is_approved(skill_input)
    assert await queue.pending() == []
