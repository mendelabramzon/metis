"""PostgresJobQueue operator surface: list, get, error_for, and retry over durable jobs."""

from __future__ import annotations

from datetime import UTC, datetime

from metis_core.jobs import PostgresJobQueue
from metis_protocol import Job, JobId, JobState, WorkspaceId, new_id

_WS = WorkspaceId("ws_" + "7" * 32)


def _job() -> Job:
    return Job(
        id=new_id(JobId),
        workspace_id=_WS,
        kind="ingest.poll",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_list_get_error_and_retry(sessionmaker):
    queue = PostgresJobQueue(sessionmaker)
    job = _job()
    await queue.enqueue(job)
    await queue.fail(job.id, "connector timeout", retry=False)

    assert [j.id for j in await queue.list(_WS)] == [job.id]
    got = await queue.get(job.id)
    assert got is not None
    assert got.state is JobState.FAILED
    assert await queue.error_for(job.id) == "connector timeout"

    revived = await queue.retry(job.id)
    assert revived is not None
    assert revived.state is JobState.PENDING
    assert revived.attempts == 1
    assert await queue.error_for(job.id) is None


async def test_retry_is_none_when_missing_or_not_retryable(sessionmaker):
    queue = PostgresJobQueue(sessionmaker)
    assert await queue.retry(new_id(JobId)) is None  # missing job

    job = _job()
    await queue.enqueue(job)  # PENDING is not a retryable state
    assert await queue.retry(job.id) is None
    assert await queue.get(new_id(JobId)) is None
