"""The versioned event envelope, the event-name catalog, and the payload registry.

The envelope is transport-agnostic: it carries the payload as a JSON value plus a
``payload_schema_version`` and an ``event_version``. The registry maps each event
name to the schema its payload must validate against, so a consumer can decode an
envelope into a typed model and unknown event names are rejected loudly.

(The envelope's id is ``envelope_id``/``EnvelopeId``; the domain occurrence schema
owns ``EventId``, so this avoids the name clash in the plan's snippet.)
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from pydantic import AwareDatetime, Field, JsonValue

from metis_protocol.artifacts import NormalizedDoc, ParsedDoc, RawArtifact
from metis_protocol.audit import AuditEvent
from metis_protocol.claims import ExtractionBatch
from metis_protocol.enums import JobState
from metis_protocol.errors import ContractViolationError, UnknownEventError
from metis_protocol.ids import EnvelopeId, JobId, WorkspaceId, new_id
from metis_protocol.memory import (
    Contradiction,
    Foresight,
    MemCell,
    MemoryPatch,
    MemScene,
    Profile,
)
from metis_protocol.skills import SkillResult
from metis_protocol.versioning import SchemaVersion, VersionedModel, schema
from metis_protocol.wiki import WikiPage, WikiPatch


class EventName(StrEnum):
    ARTIFACT_INGESTED = "artifact.ingested"
    DOCUMENT_NORMALIZED = "document.normalized"
    DOCUMENT_PARSED = "document.parsed"
    CLAIMS_EXTRACTED = "claims.extracted"
    MEMCELL_CREATED = "memcell.created"
    MEMSCENE_UPDATED = "memscene.updated"
    PROFILE_UPDATED = "profile.updated"
    FORESIGHT_CREATED = "foresight.created"
    CONTRADICTION_DETECTED = "contradiction.detected"
    MEMORY_PATCHED = "memory.patched"
    WIKI_PATCH_PROPOSED = "wiki.patch_proposed"
    WIKI_PAGE_COMMITTED = "wiki.page_committed"
    SKILL_EXECUTED = "skill.executed"
    AUDIT_RECORDED = "audit.recorded"


class EventSpec(NamedTuple):
    payload_model: type[VersionedModel]
    event_version: int


#: Every event name resolves to the schema its payload validates against.
EVENT_REGISTRY: dict[EventName, EventSpec] = {
    EventName.ARTIFACT_INGESTED: EventSpec(RawArtifact, 1),
    EventName.DOCUMENT_NORMALIZED: EventSpec(NormalizedDoc, 1),
    EventName.DOCUMENT_PARSED: EventSpec(ParsedDoc, 1),
    EventName.CLAIMS_EXTRACTED: EventSpec(ExtractionBatch, 1),
    EventName.MEMCELL_CREATED: EventSpec(MemCell, 1),
    EventName.MEMSCENE_UPDATED: EventSpec(MemScene, 1),
    EventName.PROFILE_UPDATED: EventSpec(Profile, 1),
    EventName.FORESIGHT_CREATED: EventSpec(Foresight, 1),
    EventName.CONTRADICTION_DETECTED: EventSpec(Contradiction, 1),
    EventName.MEMORY_PATCHED: EventSpec(MemoryPatch, 1),
    EventName.WIKI_PATCH_PROPOSED: EventSpec(WikiPatch, 1),
    EventName.WIKI_PAGE_COMMITTED: EventSpec(WikiPage, 1),
    EventName.SKILL_EXECUTED: EventSpec(SkillResult, 1),
    EventName.AUDIT_RECORDED: EventSpec(AuditEvent, 1),
}


def payload_spec(name: EventName) -> EventSpec:
    """The payload spec for an event name, or ``UnknownEventError`` if unregistered."""
    try:
        return EVENT_REGISTRY[name]
    except KeyError as exc:
        raise UnknownEventError(str(name)) from exc


@schema
class EventEnvelope(VersionedModel):
    """A versioned, transport-agnostic event wrapper."""

    envelope_id: EnvelopeId
    event_name: EventName
    event_version: int
    occurred_at: AwareDatetime
    workspace_id: WorkspaceId
    trace_id: str
    payload_schema_version: SchemaVersion
    payload: JsonValue


def build_envelope(
    *,
    event_name: EventName,
    payload: VersionedModel,
    workspace_id: WorkspaceId,
    occurred_at: AwareDatetime,
    trace_id: str,
    envelope_id: EnvelopeId | None = None,
) -> EventEnvelope:
    """Wrap a typed payload in an envelope, stamping the registered version."""
    spec = payload_spec(event_name)
    if not isinstance(payload, spec.payload_model):
        raise ContractViolationError(
            f"event {event_name!r} expects {spec.payload_model.__name__}, "
            f"got {type(payload).__name__}"
        )
    return EventEnvelope(
        envelope_id=envelope_id if envelope_id is not None else new_id(EnvelopeId),
        event_name=event_name,
        event_version=spec.event_version,
        occurred_at=occurred_at,
        workspace_id=workspace_id,
        trace_id=trace_id,
        payload_schema_version=payload.schema_version,
        payload=payload.model_dump(mode="json"),
    )


def decode_payload(envelope: EventEnvelope) -> VersionedModel:
    """Validate an envelope's payload back into its typed model."""
    spec = payload_spec(envelope.event_name)
    return spec.payload_model.model_validate(envelope.payload)


@schema
class Job(VersionedModel):
    """A unit of background work managed by a ``JobQueue``."""

    id: JobId
    workspace_id: WorkspaceId
    kind: str
    state: JobState = JobState.PENDING
    payload: JsonValue = Field(default_factory=dict)
    attempts: int = 0
    created_at: AwareDatetime
    scheduled_at: AwareDatetime | None = None
