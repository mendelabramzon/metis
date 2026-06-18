"""The job queue is safe under concurrent workers (FOR UPDATE SKIP LOCKED)."""

import asyncio
from datetime import UTC, datetime

from metis_core.jobs import PostgresJobQueue
from metis_core.models import JobRow
from metis_protocol import Job, JobId, JobState, new_id
from metis_protocol.examples import WS


def _job(kind: str = "ingest") -> Job:
    return Job(id=new_id(JobId), workspace_id=WS, kind=kind, created_at=datetime.now(UTC))


async def test_concurrent_leases_are_disjoint(sessionmaker):
    queue = PostgresJobQueue(sessionmaker)
    for _ in range(6):
        await queue.enqueue(_job())

    first, second = await asyncio.gather(
        queue.lease(["ingest"], 3),
        queue.lease(["ingest"], 3),
    )
    ids_first = {job.id for job in first}
    ids_second = {job.id for job in second}
    assert not (ids_first & ids_second)  # no job leased twice
    assert len(ids_first | ids_second) == 6


async def test_fail_with_retry_reschedules(sessionmaker):
    queue = PostgresJobQueue(sessionmaker)
    job = _job()
    await queue.enqueue(job)

    leased = await queue.lease(["ingest"], 1)
    assert len(leased) == 1

    await queue.fail(job.id, "boom", retry=True)
    async with sessionmaker() as session:
        row = await session.get(JobRow, str(job.id))
        assert row is not None
        assert row.state == JobState.RETRYING.value
        assert row.scheduled_at is not None
