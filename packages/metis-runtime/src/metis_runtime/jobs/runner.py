"""The runtime worker: lease jobs from the core JobQueue and dispatch via the registry.

Extends the core ``Worker`` lease/handle/ack loop (the same base the maintainer worker uses). Each
leased job is routed to its registered handler by ``kind``, run against the shared
:class:`RuntimeDeps`, and recorded on the audit trail. An unknown kind fails without retry (it will
never become runnable); handler errors propagate to the base loop, which retries with backoff.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from metis_core import Worker
from metis_protocol import (
    AgentKind,
    Attribution,
    AuditEvent,
    AuditId,
    AuditSink,
    Job,
    JobQueue,
    Sensitivity,
    WorkspaceId,
    new_id,
)
from metis_runtime.jobs.base import RuntimeDeps, RuntimeJob, RuntimeJobOutcome
from metis_runtime.jobs.registry import build_runtime_registry


class UnknownRuntimeJobError(Exception):
    """A leased job names a kind with no registered handler (do not retry)."""


class RuntimeWorker(Worker):
    def __init__(
        self,
        queue: JobQueue,
        deps: RuntimeDeps,
        *,
        registry: dict[str, RuntimeJob] | None = None,
        kinds: Sequence[str] | None = None,
        batch_size: int = 10,
    ) -> None:
        self._registry = registry if registry is not None else build_runtime_registry()
        self._deps = deps
        super().__init__(
            queue, kinds if kinds is not None else list(self._registry), batch_size=batch_size
        )

    async def handle(self, job: Job) -> None:
        handler = self._registry.get(job.kind)
        if handler is None:
            raise UnknownRuntimeJobError(job.kind)
        payload: dict[str, Any] = {"workspace_id": str(job.workspace_id), **_payload(job.payload)}
        outcome = await handler.run(self._deps, payload)
        await _record(self._deps.audit_sink, workspace_id=job.workspace_id, outcome=outcome)


def _payload(payload: object) -> Mapping[str, Any]:
    return payload if isinstance(payload, dict) else {}


async def _record(
    audit_sink: AuditSink, *, workspace_id: WorkspaceId, outcome: RuntimeJobOutcome
) -> None:
    """Emit a ``runtime.<kind>`` audit event per run, so background work stays inspectable."""
    await audit_sink.emit(
        AuditEvent(
            id=new_id(AuditId),
            workspace_id=workspace_id,
            occurred_at=datetime.now(UTC),
            actor=Attribution(agent_kind=AgentKind.SYSTEM, agent="runtime-worker"),
            action=outcome.kind,
            sensitivity=Sensitivity.INTERNAL,
            payload={"summary": outcome.summary, "counts": dict(outcome.counts)},
        )
    )
