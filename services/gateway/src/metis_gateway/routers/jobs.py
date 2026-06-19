"""Jobs/ops: inspect jobs and retry failed ones (the operator's failure-recovery surface).

Backed by ``backend.jobs`` — the in-memory queue for the dev backend, the durable Postgres queue for
the server — behind one ``JobOps`` interface, so this router is identical for both.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.backend import Backend
from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.errors import ConflictError, NotFoundError
from metis_gateway.schemas import JobView
from metis_protocol import Job, JobId

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _view(backend: Backend, job: Job) -> JobView:
    return JobView(
        id=str(job.id),
        kind=job.kind,
        state=job.state,
        attempts=job.attempts,
        error=await backend.jobs.error_for(job.id),
    )


@router.get("", response_model=list[JobView])
async def list_jobs(backend: BackendDep, _principal: OperatorDep) -> list[JobView]:
    jobs = await backend.jobs.list(backend.workspace_id)
    return [await _view(backend, job) for job in jobs]


@router.get("/{job_id}", response_model=JobView)
async def get_job(job_id: str, backend: BackendDep, _principal: OperatorDep) -> JobView:
    job = await backend.jobs.get(JobId(job_id))
    if job is None:
        raise NotFoundError(f"no job {job_id!r}")
    return await _view(backend, job)


@router.post("/{job_id}/retry", response_model=JobView)
async def retry_job(job_id: str, backend: BackendDep, _principal: OperatorDep) -> JobView:
    if await backend.jobs.get(JobId(job_id)) is None:
        raise NotFoundError(f"no job {job_id!r}")
    revived = await backend.jobs.retry(JobId(job_id))
    if revived is None:
        raise ConflictError(f"job {job_id!r} is not in a retryable state")
    return await _view(backend, revived)
