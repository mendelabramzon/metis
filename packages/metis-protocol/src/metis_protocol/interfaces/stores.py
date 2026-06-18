"""Durable store interfaces implemented by ``metis-core``. All are async (ADR 0008).

These are the contracts the abstract suites in ``metis_protocol.contract_tests``
exercise, so an implementation can prove conformance before it is trusted.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from metis_protocol.artifacts import NormalizedDoc, ParsedDoc, RawArtifact, Segment
from metis_protocol.claims import Claim, ClaimWriteResult, ExtractionBatch
from metis_protocol.ids import (
    ClaimId,
    DocId,
    MemCellId,
    MemSceneId,
    ParsedDocId,
    SegmentId,
    WikiPageId,
)
from metis_protocol.memory import MemCell, MemoryPatch, MemScene
from metis_protocol.query import ClaimFilter, MemoryScope
from metis_protocol.refs import ArtifactRef
from metis_protocol.wiki import WikiPage, WikiPatch


@runtime_checkable
class ArtifactStore(Protocol):
    async def put(self, raw: RawArtifact) -> ArtifactRef: ...

    async def get(self, ref: ArtifactRef) -> RawArtifact | None: ...


@runtime_checkable
class DocumentStore(Protocol):
    async def put_normalized(self, doc: NormalizedDoc) -> DocId: ...

    async def get_normalized(self, doc_id: DocId) -> NormalizedDoc | None: ...

    async def put_parsed(self, doc: ParsedDoc) -> ParsedDocId: ...

    async def get_parsed(self, parsed_doc_id: ParsedDocId) -> ParsedDoc | None: ...

    async def put_segments(self, segments: Sequence[Segment]) -> Sequence[SegmentId]: ...

    async def get_segment(self, segment_id: SegmentId) -> Segment | None: ...


@runtime_checkable
class ClaimStore(Protocol):
    async def write(self, batch: ExtractionBatch) -> ClaimWriteResult: ...

    async def query(self, claim_filter: ClaimFilter) -> Sequence[Claim]: ...

    async def get(self, claim_id: ClaimId) -> Claim | None: ...


@runtime_checkable
class MemoryStore(Protocol):
    async def write_mem_cell(self, cell: MemCell) -> MemCellId: ...

    async def get_mem_cell(self, mem_cell_id: MemCellId) -> MemCell | None: ...

    async def write_scene(self, scene: MemScene) -> MemSceneId: ...

    async def get_scene(self, mem_scene_id: MemSceneId) -> MemScene | None: ...

    async def apply_patch(self, patch: MemoryPatch) -> None: ...

    async def query_cells(self, scope: MemoryScope) -> Sequence[MemCell]: ...


@runtime_checkable
class WikiStore(Protocol):
    async def get_page(self, wiki_page_id: WikiPageId) -> WikiPage | None: ...

    async def get_page_by_slug(self, slug: str) -> WikiPage | None: ...

    async def apply_patch(self, patch: WikiPatch) -> WikiPageId: ...
