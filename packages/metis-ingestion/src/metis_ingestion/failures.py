"""Non-fatal failure recording: a parse/extract error is logged as an audit event and
the pipeline continues with sibling artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_ingestion._build import make_provenance, now_utc
from metis_protocol import (
    AgentKind,
    AuditEvent,
    AuditId,
    AuditSink,
    Sensitivity,
    WorkspaceId,
    new_id,
)


class IngestionError(Exception):
    """Base class for ingestion errors."""


class UnsupportedMediaType(IngestionError):
    """No parser is registered for a media type."""


class ParseError(IngestionError):
    """A parser failed on an artifact's bytes."""


class ExtractError(IngestionError):
    """The extractor failed on a parsed document."""


@dataclass(frozen=True)
class StepFailure:
    step: str
    locator: str | None
    error_type: str
    message: str


async def record_failure(
    audit_sink: AuditSink,
    *,
    workspace_id: WorkspaceId,
    step: str,
    target_id: str | None,
    error: Exception,
) -> StepFailure:
    """Emit an audit event for a failed step and return a structured failure."""
    failure = StepFailure(
        step=step,
        locator=target_id,
        error_type=type(error).__name__,
        message=str(error),
    )
    event = AuditEvent(
        id=new_id(AuditId),
        workspace_id=workspace_id,
        occurred_at=now_utc(),
        actor=make_provenance(
            workspace_id, agent_kind=AgentKind.SYSTEM, agent="metis-ingestion"
        ).attribution,
        action=f"ingest.failure.{step}",
        target_id=target_id,
        sensitivity=Sensitivity.INTERNAL,
        payload={"error_type": failure.error_type, "message": failure.message},
    )
    await audit_sink.emit(event)
    return failure
