"""ConnectorSyncWorker: the lease half of the queued-connector path. A scheduled ``ingest.poll``
job is leased and run through a DurableIngestPoller (durable cursor + run history), then acked; a
job for an unknown source is failed for retry rather than lost."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from metis_ingestion import ConnectorSyncWorker, IngestResult
from metis_ingestion.connectors.scheduling import POLL_JOB_KIND
from metis_protocol import (
    Job,
    JobId,
    Sensitivity,
    SourceConfig,
    SourceCursor,
    SourceId,
    WorkspaceId,
    new_id,
)

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _source() -> SourceConfig:
    return SourceConfig(
        id=new_id(SourceId),
        workspace_id=new_id(WorkspaceId),
        name="mailbox",
        connector="imap",
        sensitivity=Sensitivity.CONFIDENTIAL,
        auth_method="basic",
        created_at=_T,
    )


def _poll_job(source_id: str, workspace_id: WorkspaceId) -> Job:
    return Job(
        id=new_id(JobId),
        workspace_id=workspace_id,
        kind=POLL_JOB_KIND,
        payload={"connector": "imap", "source_id": source_id, "cursor": None},
        created_at=_T,
    )


class _FakeQueue:
    def __init__(self, jobs: Sequence[Job]) -> None:
        self._pending = list(jobs)
        self.completed: list[JobId] = []
        self.failed: list[tuple[JobId, bool]] = []

    async def enqueue(self, job: Job) -> JobId:
        self._pending.append(job)
        return job.id

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]:
        leased = self._pending[:limit]
        self._pending = self._pending[limit:]
        return leased

    async def complete(self, job_id: JobId) -> None:
        self.completed.append(job_id)

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None:
        self.failed.append((job_id, retry))


class _FakeSourceStore:
    def __init__(self, sources: dict[str, SourceConfig]) -> None:
        self._sources = sources
        self.saved_cursors: list[SourceCursor] = []

    async def get(self, source_id: SourceId) -> SourceConfig | None:
        return self._sources.get(str(source_id))

    async def get_cursor(self, source_id: SourceId) -> SourceCursor | None:
        return None

    async def set_cursor(self, cursor: SourceCursor) -> SourceCursor:
        self.saved_cursors.append(cursor)
        return cursor

    async def record_run(self, run: object) -> object:
        return run


class _FakePipeline:
    def __init__(self, result: IngestResult) -> None:
        self._result = result
        self.runs = 0

    async def run(self, *, cursor: str | None = None) -> IngestResult:
        self.runs += 1
        return self._result


async def test_a_queued_poll_job_runs_the_source_sync_and_is_acked() -> None:
    source = _source()
    pipeline = _FakePipeline(IngestResult(artifacts=2, claims=3, failures=(), next_cursor="uid-7"))
    store = _FakeSourceStore({str(source.id): source})
    job = _poll_job(str(source.id), source.workspace_id)
    queue = _FakeQueue([job])
    worker = ConnectorSyncWorker(queue, sources=store, pipeline_factory=lambda _s: pipeline)

    handled = await worker.run_once()

    assert handled == 1
    assert pipeline.runs == 1  # the connector synced via the queued job
    assert queue.completed == [job.id]  # the job was acked
    assert [c.cursor for c in store.saved_cursors] == ["uid-7"]  # durable cursor advanced


async def test_a_job_for_an_unknown_source_is_failed_for_retry() -> None:
    pipeline = _FakePipeline(IngestResult(artifacts=0, claims=0, failures=(), next_cursor=None))
    store = _FakeSourceStore({})  # the source was deleted/never registered
    job = _poll_job("src_" + "0" * 32, new_id(WorkspaceId))
    queue = _FakeQueue([job])
    worker = ConnectorSyncWorker(queue, sources=store, pipeline_factory=lambda _s: pipeline)

    handled = await worker.run_once()

    assert handled == 1
    assert queue.completed == []
    assert queue.failed == [(job.id, True)]  # reschedule with backoff, do not drop the job
