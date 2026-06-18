"""Maintenance audit trail: record every maintainer job run as an audit event.

Each run emits a ``maintain.<kind>`` event attributed to the maintainer, carrying the job's
summary and effect counts, onto the same append-only, hash-chained audit log the stores and
model calls use (via the core ``AuditSink``). So every background change is inspectable.
"""

from __future__ import annotations

from metis_maintainer.jobs.base import JobOutcome
from metis_maintainer.memory._build import now_utc
from metis_protocol import (
    AgentKind,
    Attribution,
    AuditEvent,
    AuditId,
    AuditSink,
    Sensitivity,
    WorkspaceId,
    new_id,
)


async def record_job_run(
    audit_sink: AuditSink, *, workspace_id: WorkspaceId, outcome: JobOutcome
) -> None:
    """Emit a ``maintain.<kind>`` audit event for a completed job run."""
    await audit_sink.emit(
        AuditEvent(
            id=new_id(AuditId),
            workspace_id=workspace_id,
            occurred_at=now_utc(),
            actor=Attribution(agent_kind=AgentKind.MAINTAINER, agent=outcome.kind),
            action=f"maintain.{outcome.kind}",
            sensitivity=Sensitivity.INTERNAL,
            payload={"summary": outcome.summary, "counts": dict(outcome.counts)},
        )
    )
