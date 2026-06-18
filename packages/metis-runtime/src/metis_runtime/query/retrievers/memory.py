"""The memory retriever: the ``Retriever`` over interpreted memory.

Composes the Stage 5 hybrid lookup (pgvector + FTS + reciprocal rank fusion) — the runtime does
not re-implement hybrid search, it reuses the core primitive — and enforces the requester's
sensitivity ceiling: a cell more restrictive than ``query.max_sensitivity`` is dropped before it
can reach packing or an answer. Returns the cited claim/source-span refs an answer must ground in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from metis_core.memory_index import MemoryIndexLookup
from metis_protocol import (
    ClaimRef,
    EvidenceSet,
    EvidenceSetId,
    MemCell,
    MemCellRef,
    QueryRequest,
    SourceSpanRef,
    is_at_least,
    new_id,
)


class MemoryRetriever:
    def __init__(self, lookup: MemoryIndexLookup) -> None:
        self._lookup = lookup

    async def retrieve(self, query: QueryRequest) -> EvidenceSet:
        evidence, _ = await self.retrieve_cells(query)
        return evidence

    async def retrieve_cells(self, query: QueryRequest) -> tuple[EvidenceSet, list[MemCell]]:
        """Retrieve cells (kept, for packing) plus the EvidenceSet of refs to ground answers in."""
        hits = await self._lookup.search_mem_cells(
            workspace_id=query.workspace_id,
            query_text=query.text,
            k=query.top_k or 8,
            sensitivity=query.max_sensitivity,
        )
        # Two floors on the raw hits:
        #   - policy: never surface a cell more restrictive than the requester may see;
        #   - relevance: vector search has no similarity threshold, so it returns the nearest
        #     cell even when unrelated. Require lexical overlap with the query as a deterministic
        #     relevance floor (a stand-in for a similarity cutoff / reranker, added later).
        query_terms = _content_terms(query.text)
        cells = [
            hit.item
            for hit in hits
            if is_at_least(query.max_sensitivity, hit.item.policy.sensitivity)
            and (
                not query_terms
                or query_terms & _content_terms(f"{hit.item.summary} {hit.item.content}")
            )
        ]
        evidence = EvidenceSet(
            id=new_id(EvidenceSetId),
            query_id=query.id,
            claims=_dedup_claims(ref for cell in cells for ref in cell.claims),
            source_spans=_dedup_spans(ref for cell in cells for ref in cell.source_spans),
            mem_cells=tuple(MemCellRef(mem_cell_id=cell.id) for cell in cells),
        )
        return evidence, cells


_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    ]
)


def _content_terms(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS}


def _dedup_claims(refs: Iterable[ClaimRef]) -> tuple[ClaimRef, ...]:
    seen: set[str] = set()
    out: list[ClaimRef] = []
    for ref in refs:
        if str(ref.claim_id) not in seen:
            seen.add(str(ref.claim_id))
            out.append(ref)
    return tuple(out)


def _dedup_spans(refs: Iterable[SourceSpanRef]) -> tuple[SourceSpanRef, ...]:
    seen: set[str] = set()
    out: list[SourceSpanRef] = []
    for ref in refs:
        if str(ref.source_span_id) not in seen:
            seen.add(str(ref.source_span_id))
            out.append(ref)
    return tuple(out)


if TYPE_CHECKING:
    from metis_protocol import Retriever

    def _conforms(retriever: MemoryRetriever) -> Retriever:
        return retriever  # static proof of the Retriever protocol
