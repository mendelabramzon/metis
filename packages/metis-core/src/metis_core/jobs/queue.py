"""``PostgresJobQueue``: a job queue over Postgres using ``FOR UPDATE SKIP LOCKED``.

Concurrent workers never lease the same job (the lease transaction locks and skips
already-locked rows). ``fail(retry=True)`` reschedules with exponential backoff.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core._util import now_utc
from metis_core.db.session import unit_of_work
from metis_core.mappers import job_to_row, to_model
from metis_core.models import JobRow
from metis_protocol import Job, JobId, JobState, WorkspaceId

_LEASABLE = (JobState.PENDING.value, JobState.RETRYING.value)
_MAX_BACKOFF_SECONDS = 300


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2**attempts, _MAX_BACKOFF_SECONDS))


def _sync_body(row: JobRow) -> None:
    """Keep the JSONB body consistent with the mutated state columns."""
    body = dict(row.body)
    body["state"] = row.state
    body["attempts"] = row.attempts
    body["scheduled_at"] = row.scheduled_at.isoformat() if row.scheduled_at is not None else None
    row.body = body


class PostgresJobQueue:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def enqueue(self, job: Job) -> JobId:
        # Idempotent by id: enqueuing a job whose id already exists is a no-op, so a
        # scheduler can derive a deterministic id per unit of work and enqueue freely
        # without forking duplicate jobs (Stage 6 relies on this).
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(JobRow, str(job.id)) is None:
                session.add(job_to_row(job))
        return job.id

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]:
        now = now_utc()
        stmt = (
            select(JobRow)
            .where(
                JobRow.kind.in_(list(kinds)),
                JobRow.state.in_(_LEASABLE),
                or_(JobRow.scheduled_at.is_(None), JobRow.scheduled_at <= now),
            )
            .order_by(JobRow.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
            leased: list[Job] = []
            for row in rows:
                row.state = JobState.RUNNING.value
                row.attempts = row.attempts + 1
                row.locked_at = now
                _sync_body(row)
                leased.append(to_model(row, Job))
        return leased

    async def complete(self, job_id: JobId) -> None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(JobRow, str(job_id))
            if row is not None:
                row.state = JobState.SUCCEEDED.value
                row.locked_at = None
                _sync_body(row)

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(JobRow, str(job_id))
            if row is None:
                return
            row.last_error = error
            row.locked_at = None
            if retry:
                row.state = JobState.RETRYING.value
                row.scheduled_at = now_utc() + _backoff(row.attempts)
            else:
                row.state = JobState.FAILED.value
            _sync_body(row)

    # --- operator inspect/retry surface ------------------------------------------------------

    async def list(self, workspace_id: WorkspaceId, *, limit: int = 200) -> Sequence[Job]:
        """Recent jobs in the workspace, newest first (the operator's inspect surface)."""
        stmt = (
            select(JobRow)
            .where(JobRow.workspace_id == str(workspace_id))
            .order_by(JobRow.created_at.desc())
            .limit(limit)
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, Job) for row in rows]

    async def get(self, job_id: JobId) -> Job | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(JobRow, str(job_id))
        return to_model(row, Job) if row is not None else None

    async def error_for(self, job_id: JobId) -> str | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(JobRow, str(job_id))
        return row.last_error if row is not None else None

    async def retry(self, job_id: JobId) -> Job | None:
        """Revive a FAILED/RETRYING job to PENDING (attempts+1, error cleared). Returns ``None`` if
        the job is missing or not in a retryable state."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(JobRow, str(job_id))
            if row is None or row.state not in (JobState.FAILED.value, JobState.RETRYING.value):
                return None
            row.state = JobState.PENDING.value
            row.attempts = row.attempts + 1
            row.last_error = None
            row.scheduled_at = None
            _sync_body(row)
            return to_model(row, Job)
