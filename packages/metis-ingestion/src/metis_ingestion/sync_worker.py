"""Lease scheduled connector-poll jobs from the durable queue and run them.

``ConnectorScheduler`` enqueues an ``ingest.poll`` job per source; ``ConnectorSyncWorker`` is the
other half — it leases those jobs and runs the source's sync through a :class:`DurableIngestPoller`,
so a connector syncs end-to-end via a *queued* job rather than an inline call. The core ``Worker``
base acks a completed job and reschedules a failed one with backoff, so a transient provider failure
retries without losing the job; the durable cursor means the retry resumes where the sync left off.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from metis_core.jobs import Worker
from metis_ingestion.connectors.scheduling import POLL_JOB_KIND
from metis_ingestion.poller import DurableIngestPoller, Pipeline
from metis_protocol import Job, JobQueue, SourceConfig, SourceId, SourceStore


class ConnectorSyncWorker(Worker):
    """Runs queued ``ingest.poll`` jobs: resolve the source, sync it durably, then ack/retry.

    ``pipeline_factory`` builds the ingestion pipeline for a resolved source (its connector over the
    core stores); it is *async* so a connector that must resolve a credential first — an OAuth token
    for Google Drive — can do so before the sync's synchronous transport reads. The worker resumes
    that source's durable cursor and records a connector run, so a queued sync produces exactly the
    same evidence and history as a direct poll.
    """

    def __init__(
        self,
        queue: JobQueue,
        *,
        sources: SourceStore,
        pipeline_factory: Callable[[SourceConfig], Awaitable[Pipeline]],
        batch_size: int = 10,
    ) -> None:
        super().__init__(queue, [POLL_JOB_KIND], batch_size=batch_size)
        self._sources = sources
        self._pipeline_factory = pipeline_factory

    async def handle(self, job: Job) -> None:
        source = await self._resolve(job)
        pipeline = await self._pipeline_factory(source)
        poller = await DurableIngestPoller.resume(pipeline, source=source, store=self._sources)
        await poller.poll_once()

    async def _resolve(self, job: Job) -> SourceConfig:
        payload = job.payload if isinstance(job.payload, dict) else {}
        source_id = payload.get("source_id")
        if not isinstance(source_id, str):
            raise ValueError(f"poll job {job.id} carries no source_id")
        source = await self._sources.get(SourceId(source_id))
        if source is None:
            raise ValueError(f"poll job {job.id} references unknown source {source_id!r}")
        return source
