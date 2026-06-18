"""Typed references between artifacts.

A reference is a thin, typed pointer to another artifact. Most wrap a single ID;
``SourceSpanRef`` denormalizes the owning artifact/doc so evidence can be resolved
without a join. Using refs (not bare IDs) at field sites keeps "claim where entity
expected" a type error.
"""

from __future__ import annotations

from metis_protocol.base import ProtocolModel
from metis_protocol.ids import (
    ArtifactId,
    ClaimId,
    DocId,
    EntityId,
    EventId,
    MemCellId,
    MemSceneId,
    ParsedDocId,
    SegmentId,
    SourceSpanId,
    WikiPageId,
    WorkspaceId,
)


class WorkspaceRef(ProtocolModel):
    workspace_id: WorkspaceId


class ArtifactRef(ProtocolModel):
    artifact_id: ArtifactId


class DocRef(ProtocolModel):
    doc_id: DocId


class ParsedDocRef(ProtocolModel):
    parsed_doc_id: ParsedDocId


class SegmentRef(ProtocolModel):
    segment_id: SegmentId


class SourceSpanRef(ProtocolModel):
    """Evidence pointer. Carries the owning artifact (and doc) for direct resolution."""

    source_span_id: SourceSpanId
    artifact_id: ArtifactId
    doc_id: DocId | None = None


class ClaimRef(ProtocolModel):
    claim_id: ClaimId


class EntityRef(ProtocolModel):
    entity_id: EntityId


class EventRef(ProtocolModel):
    event_id: EventId


class MemCellRef(ProtocolModel):
    mem_cell_id: MemCellId


class MemSceneRef(ProtocolModel):
    mem_scene_id: MemSceneId


class WikiPageRef(ProtocolModel):
    wiki_page_id: WikiPageId
