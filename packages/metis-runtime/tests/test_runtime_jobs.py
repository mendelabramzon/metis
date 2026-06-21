"""The runtime job framework: the research handler files answers back; the worker dispatches.

All over fakes (a scripted answerer + an in-memory inbox/queue/audit) — the handler logic and the
lease/dispatch/audit loop, no Postgres. The real engine wiring is exercised by the service boot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metis_protocol import (
    AuditEvent,
    ClaimId,
    ClaimRef,
    Job,
    JobId,
    QueryId,
    QueryRequest,
    WorkspaceId,
    new_id,
)
from metis_runtime import RuntimeWorker, build_research_job
from metis_runtime.jobs import RESEARCH_JOB_KIND, ResearchJob, RuntimeDeps
from metis_runtime.query import Answer

_WS = new_id(WorkspaceId)


class _FakeAnswerer:
    def __init__(self, answer: Answer) -> None:
        self._answer = answer

    async def answer(self, query: QueryRequest) -> Answer:
        return self._answer


class _FakeInbox:
    def __init__(self) -> None:
        self.proposed: list[Any] = []

    async def propose(self, review: Any) -> None:
        self.proposed.append(review)


class _RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class _FakeQueue:
    """A minimal JobQueue for run_once: leases the seeded jobs, records complete/fail."""

    def __init__(self, jobs: Sequence[Job]) -> None:
        self._jobs = list(jobs)
        self.completed: list[JobId] = []
        self.failed: list[tuple[JobId, bool]] = []

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]:
        leased = [j for j in self._jobs if j.kind in kinds][:limit]
        self._jobs = [j for j in self._jobs if j not in leased]
        return leased

    async def complete(self, job_id: JobId) -> None:
        self.completed.append(job_id)

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None:
        self.failed.append((job_id, retry))


def _deps(answer: Answer, inbox: _FakeInbox) -> tuple[RuntimeDeps, _RecordingAudit]:
    audit = _RecordingAudit()
    deps = RuntimeDeps(
        query_engine=_FakeAnswerer(answer), wiki_inbox=lambda _ws: inbox, audit_sink=audit
    )
    return deps, audit


def _answer(*, text: str, sufficient: bool) -> Answer:
    claims = (ClaimRef(claim_id=new_id(ClaimId)),) if sufficient else ()
    return Answer(query_id=new_id(QueryId), text=text, claims=claims, sufficient=sufficient)


def _payload(**extra: Any) -> Mapping[str, Any]:
    return {"workspace_id": str(_WS), **extra}


async def test_research_files_a_proposal_when_grounded() -> None:
    inbox = _FakeInbox()
    deps, _audit = _deps(_answer(text="Acme ships in 2026.", sufficient=True), inbox)
    outcome = await ResearchJob().run(deps, _payload(query="when does Acme ship?"))
    assert outcome.counts["filed"] == 1
    assert len(inbox.proposed) == 1
    assert inbox.proposed[0].patch.body_markdown == "Acme ships in 2026."  # the answer, filed back


async def test_research_files_nothing_when_insufficient() -> None:
    inbox = _FakeInbox()
    deps, _audit = _deps(_answer(text="not enough evidence", sufficient=False), inbox)
    outcome = await ResearchJob().run(deps, _payload(query="x"))
    assert outcome.counts["filed"] == 0
    assert inbox.proposed == []  # never files an ungrounded answer


async def test_research_without_a_query_files_nothing() -> None:
    inbox = _FakeInbox()
    deps, _audit = _deps(_answer(text="anything", sufficient=True), inbox)
    outcome = await ResearchJob().run(deps, _payload())
    assert outcome.counts["filed"] == 0


def test_build_research_job_carries_kind_and_payload() -> None:
    job = build_research_job(workspace_id=_WS, query="hello")
    assert job.kind == RESEARCH_JOB_KIND
    assert job.payload["query"] == "hello"
    assert job.payload["workspace_id"] == str(_WS)


async def test_worker_dispatches_research_and_audits() -> None:
    inbox = _FakeInbox()
    deps, audit = _deps(_answer(text="Acme ships in 2026.", sufficient=True), inbox)
    job = build_research_job(workspace_id=_WS, query="when does Acme ship?")
    queue = _FakeQueue([job])

    handled = await RuntimeWorker(queue, deps).run_once()

    assert handled == 1
    assert queue.completed == [job.id]  # acked on success
    assert len(inbox.proposed) == 1  # the job's effect ran
    assert any(e.action == RESEARCH_JOB_KIND for e in audit.events)  # and the run is audited
