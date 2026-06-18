"""Machine truth: claims, entities, events, and the extraction batch that carries
them out of ingestion.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field

from metis_protocol.artifacts import Artifact
from metis_protocol.base import ProtocolModel
from metis_protocol.enums import EntityKind
from metis_protocol.ids import (
    BatchId,
    ClaimId,
    EntityId,
    EventId,
    ParsedDocId,
    WorkspaceId,
)
from metis_protocol.provenance import Provenance
from metis_protocol.refs import EntityRef, SourceSpanRef
from metis_protocol.versioning import VersionedModel, schema


@schema
class Entity(Artifact[EntityId]):
    """A person, organization, project, etc., aggregated across evidence."""

    kind: EntityKind
    name: str
    aliases: tuple[str, ...] = ()
    description: str | None = None
    source_spans: tuple[SourceSpanRef, ...] = ()


@schema
class Event(Artifact[EventId]):
    """A dated occurrence extracted from evidence."""

    summary: str
    occurred_at: AwareDatetime | None = None
    participants: tuple[EntityRef, ...] = ()
    source_spans: tuple[SourceSpanRef, ...] = ()


@schema
class Claim(Artifact[ClaimId]):
    """An atomic assertion. Every claim cites evidence: ``source_spans`` is non-empty."""

    text: str
    predicate: str | None = None
    subject_ref: EntityRef | None = None
    object_ref: EntityRef | None = None
    source_spans: tuple[SourceSpanRef, ...] = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    negated: bool = False


@schema
class ExtractionBatch(VersionedModel):
    """The output of extracting one parsed doc: the unit a ``ClaimStore`` writes."""

    id: BatchId
    workspace_id: WorkspaceId
    parsed_doc_id: ParsedDocId
    provenance: Provenance
    claims: tuple[Claim, ...] = ()
    entities: tuple[Entity, ...] = ()
    events: tuple[Event, ...] = ()


class ClaimWriteResult(ProtocolModel):
    """The result of persisting an extraction batch (returned by ``ClaimStore.write``)."""

    written_claims: tuple[ClaimId, ...] = ()
    written_entities: tuple[EntityId, ...] = ()
    written_events: tuple[EventId, ...] = ()
    skipped: int = 0
