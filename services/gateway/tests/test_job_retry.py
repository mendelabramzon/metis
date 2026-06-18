"""A failed job can be inspected and retried via the ops API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from metis_protocol import Job, JobId, new_id


def _seed_failed_job(client) -> str:
    """Simulate a worker that enqueued then failed a job (no enqueue endpoint by design)."""
    backend = client.app.state.backend
    job = Job(
        id=new_id(JobId),
        workspace_id=backend.workspace_id,
        kind="ingest.poll",
        created_at=datetime.now(UTC),
    )
    asyncio.run(backend.jobs.enqueue(job))
    asyncio.run(backend.jobs.fail(job.id, "connector timeout", retry=False))
    return str(job.id)


def test_failed_job_is_inspectable_and_retryable(client, op) -> None:
    job_id = _seed_failed_job(client)

    inspected = client.get(f"/jobs/{job_id}", headers=op).json()
    assert inspected["state"] == "failed"
    assert inspected["error"] == "connector timeout"
    assert any(job["id"] == job_id for job in client.get("/jobs", headers=op).json())

    retried = client.post(f"/jobs/{job_id}/retry", headers=op)
    assert retried.status_code == 200
    assert retried.json()["state"] == "pending"
    assert retried.json()["attempts"] == 1


def test_retrying_an_unknown_job_is_404(client, op) -> None:
    assert (
        client.post("/jobs/job_00000000000000000000000000000000/retry", headers=op).status_code
        == 404
    )
