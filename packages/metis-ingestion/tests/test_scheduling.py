"""Scheduling: a poll is due on its interval and carries the cursor; unsigned webhooks refused."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from metis_ingestion.connectors import (
    ConnectorScheduler,
    WebhookVerificationError,
    poll_due,
)
from metis_ingestion.connectors.scheduling import POLL_JOB_KIND, WEBHOOK_JOB_KIND
from metis_protocol import Job, JobId, SourceId, WorkspaceId, new_id

WS = WorkspaceId(f"ws_{'a' * 32}")


class RecordingQueue:
    """A minimal in-process ``JobQueue`` that records what was enqueued."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []

    async def enqueue(self, job: Job) -> JobId:
        self.jobs.append(job)
        return job.id

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]:
        return []

    async def complete(self, job_id: JobId) -> None: ...

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None: ...


def test_poll_due_respects_interval() -> None:
    now = datetime(2026, 6, 19, tzinfo=UTC)
    assert poll_due(last_run=None, interval_seconds=300, now=now)  # never run -> due
    assert not poll_due(last_run=now - timedelta(seconds=60), interval_seconds=300, now=now)
    assert poll_due(last_run=now - timedelta(seconds=600), interval_seconds=300, now=now)


async def test_poll_job_carries_cursor_for_resume() -> None:
    queue = RecordingQueue()
    job_id = await ConnectorScheduler(queue).schedule_poll(
        workspace_id=WS, connector="slack", source_id=new_id(SourceId), cursor="1717236000.000300"
    )

    assert len(queue.jobs) == 1
    job = queue.jobs[0]
    assert job.id == job_id
    assert job.kind == POLL_JOB_KIND
    assert job.payload == {
        "connector": "slack",
        "source_id": job.payload["source_id"],
        "cursor": "1717236000.000300",
        "_trace": {},  # no active span here -> empty carrier (worker starts a fresh trace)
    }


async def test_unverified_webhook_is_refused_and_not_enqueued() -> None:
    queue = RecordingQueue()
    with pytest.raises(WebhookVerificationError):
        await ConnectorScheduler(queue).schedule_webhook(
            workspace_id=WS, connector="slack", event={"type": "message"}, verified=False
        )
    assert queue.jobs == []  # an unsigned payload never becomes a job


async def test_verified_webhook_enqueues_an_ingest_job() -> None:
    queue = RecordingQueue()
    await ConnectorScheduler(queue).schedule_webhook(
        workspace_id=WS, connector="slack", event={"type": "message"}, verified=True
    )
    assert len(queue.jobs) == 1
    assert queue.jobs[0].kind == WEBHOOK_JOB_KIND
