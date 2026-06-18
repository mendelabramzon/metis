"""Jobs/ops: inspect jobs and retry failed ones (the operator's failure-recovery surface)."""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.backend import Backend
from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.schemas import JobView
from metis_protocol import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _view(backend: Backend, job: Job) -> JobView:
    return JobView(
        id=str(job.id),
        kind=job.kind,
        state=job.state,
        attempts=job.attempts,
        error=backend.jobs.error_for(str(job.id)),
    )


@router.get("", response_model=list[JobView])
async def list_jobs(backend: BackendDep, _principal: OperatorDep) -> list[JobView]:
    return [_view(backend, job) for job in backend.jobs.list()]


@router.get("/{job_id}", response_model=JobView)
async def get_job(job_id: str, backend: BackendDep, _principal: OperatorDep) -> JobView:
    return _view(backend, backend.jobs.get(job_id))


@router.post("/{job_id}/retry", response_model=JobView)
async def retry_job(job_id: str, backend: BackendDep, _principal: OperatorDep) -> JobView:
    return _view(backend, backend.jobs.retry(job_id))
