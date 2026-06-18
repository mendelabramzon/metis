"""Budget-aware context packing: resolved memory cells -> a ContextBundle within a token budget.

Each retrieved cell becomes one context section carrying its claim and source-span citations, so
the downstream answer can ground every statement. Sections are emitted in retrieval-ranked order
and truncated to a token budget; the volatile per-query context comes after the (cached) frozen
instructions the answer step prepends, keeping prompts cache-friendly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from metis_protocol import (
    ContextBundle,
    ContextBundleId,
    ContextSection,
    EvidenceSet,
    MemCell,
    MemCellId,
    QueryRequest,
    new_id,
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class BudgetedContextPacker:
    def __init__(self, *, max_tokens: int = 4000) -> None:
        self._max_tokens = max_tokens

    def pack(
        self,
        query: QueryRequest,
        evidence: EvidenceSet,
        *,
        cells: Mapping[MemCellId, MemCell] | None = None,
    ) -> ContextBundle:
        resolved = cells or {}
        sections: list[ContextSection] = []
        used = 0
        for ref in evidence.mem_cells:  # retrieval-ranked order
            cell = resolved.get(ref.mem_cell_id)
            if cell is None:
                continue
            section = ContextSection(
                heading=cell.summary,
                text=cell.content,
                claims=cell.claims,
                source_spans=cell.source_spans,
            )
            tokens = _estimate_tokens(section.text) + _estimate_tokens(section.heading or "")
            if sections and used + tokens > self._max_tokens:
                break  # budget reached; keep what fits (at least one section)
            sections.append(section)
            used += tokens
        return ContextBundle(
            id=new_id(ContextBundleId),
            query_id=query.id,
            sections=tuple(sections),
            token_estimate=used,
        )


if TYPE_CHECKING:
    from metis_protocol import ContextPacker

    def _conforms(packer: BudgetedContextPacker) -> ContextPacker:
        return packer  # static proof of the ContextPacker protocol
