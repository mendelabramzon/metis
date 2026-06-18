"""Retrieval and query schemas: the request, the retrieved evidence, the packed
context bundle, plus the filter/scope value objects the interfaces consume.
"""

from __future__ import annotations

from pydantic import AwareDatetime

from metis_protocol.base import ProtocolModel
from metis_protocol.enums import Sensitivity
from metis_protocol.ids import ContextBundleId, EvidenceSetId, QueryId, WorkspaceId
from metis_protocol.refs import (
    ClaimRef,
    EntityRef,
    MemCellRef,
    MemSceneRef,
    SourceSpanRef,
    WikiPageRef,
)
from metis_protocol.versioning import VersionedModel, schema


@schema
class QueryRequest(VersionedModel):
    """A user question plus the policy ceiling the requester is allowed to see."""

    id: QueryId
    workspace_id: WorkspaceId
    text: str
    max_sensitivity: Sensitivity = Sensitivity.RESTRICTED
    top_k: int | None = None


class ContextSection(ProtocolModel):
    """One packed section of context with its supporting evidence."""

    heading: str | None = None
    text: str
    claims: tuple[ClaimRef, ...] = ()
    source_spans: tuple[SourceSpanRef, ...] = ()


@schema
class EvidenceSet(VersionedModel):
    """What retrieval found for a query, as typed references (resolved later)."""

    id: EvidenceSetId
    query_id: QueryId
    claims: tuple[ClaimRef, ...] = ()
    source_spans: tuple[SourceSpanRef, ...] = ()
    mem_cells: tuple[MemCellRef, ...] = ()
    wiki_pages: tuple[WikiPageRef, ...] = ()


@schema
class ContextBundle(VersionedModel):
    """Evidence packed into model-ready context, with a sufficiency estimate."""

    id: ContextBundleId
    query_id: QueryId
    sections: tuple[ContextSection, ...] = ()
    token_estimate: int | None = None
    sufficiency: float | None = None


class ClaimFilter(ProtocolModel):
    """A filter over claims (consumed by ``ClaimStore.query``)."""

    workspace_id: WorkspaceId
    entity: EntityRef | None = None
    predicate: str | None = None
    text_contains: str | None = None
    limit: int | None = None


class MemoryScope(ProtocolModel):
    """A scope over memory for maintenance/retrieval jobs."""

    workspace_id: WorkspaceId
    scene: MemSceneRef | None = None
    entity: EntityRef | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
