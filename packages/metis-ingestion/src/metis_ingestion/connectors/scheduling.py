"""Scheduling: turn "this source is due" (poll) or an inbound push (webhook) into ingest jobs.

Polling computes whether a source's interval has elapsed and, if so, enqueues an ingest job carrying
the source's cursor — so the worker resumes exactly where it left off rather than re-scanning. A
webhook does the same from a provider push, but a webhook payload is *untrusted* input from the open
internet, so it is only turned into a job once a signature has been verified upstream (Stage 14 owns
the keys); an unverified payload is refused, never enqueued. Both paths build a core ``Job``, so the
existing job queue/worker runs connectors with no new machinery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import JsonValue

from metis_ingestion.connectors.base import ConnectorError
from metis_protocol import Job, JobId, JobQueue, SourceId, WorkspaceId, new_id

POLL_JOB_KIND = "ingest.poll"
WEBHOOK_JOB_KIND = "ingest.webhook"


class WebhookVerificationError(ConnectorError):
    """An inbound webhook payload was not signature-verified and is refused."""


def _now() -> datetime:
    return datetime.now(UTC)


def poll_due(*, last_run: datetime | None, interval_seconds: float, now: datetime) -> bool:
    """Whether a source polled at ``last_run`` is due again at ``now``."""
    return last_run is None or (now - last_run) >= timedelta(seconds=interval_seconds)


def build_poll_job(
    *,
    workspace_id: WorkspaceId,
    connector: str,
    source_id: SourceId,
    cursor: str | None,
    now: datetime | None = None,
) -> Job:
    """A poll job that carries the cursor, so the worker resumes from that watermark."""
    return Job(
        id=new_id(JobId),
        workspace_id=workspace_id,
        kind=POLL_JOB_KIND,
        payload={"connector": connector, "source_id": str(source_id), "cursor": cursor},
        created_at=now if now is not None else _now(),
        scheduled_at=now if now is not None else _now(),
    )


def build_webhook_job(
    *,
    workspace_id: WorkspaceId,
    connector: str,
    event: JsonValue,
    verified: bool,
    now: datetime | None = None,
) -> Job:
    """A webhook-triggered ingest job; refuses an unverified (unsigned) payload."""
    if not verified:
        raise WebhookVerificationError(f"unverified webhook for {connector!r} refused")
    return Job(
        id=new_id(JobId),
        workspace_id=workspace_id,
        kind=WEBHOOK_JOB_KIND,
        payload={"connector": connector, "event": event},
        created_at=now if now is not None else _now(),
    )


class ConnectorScheduler:
    """Enqueues poll/webhook ingest jobs into the core ``JobQueue``."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    async def schedule_poll(
        self,
        *,
        workspace_id: WorkspaceId,
        connector: str,
        source_id: SourceId,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> JobId:
        job = build_poll_job(
            workspace_id=workspace_id,
            connector=connector,
            source_id=source_id,
            cursor=cursor,
            now=now,
        )
        return await self._queue.enqueue(job)

    async def schedule_webhook(
        self,
        *,
        workspace_id: WorkspaceId,
        connector: str,
        event: JsonValue,
        verified: bool,
        now: datetime | None = None,
    ) -> JobId:
        job = build_webhook_job(
            workspace_id=workspace_id,
            connector=connector,
            event=event,
            verified=verified,
            now=now,
        )
        return await self._queue.enqueue(job)
