"""The Consolidator: turn one ExtractionBatch into a persisted MemCell + a revision patch.

This is the maintainer-time entry point recommended by the Stage 5 plan (driven by the
``claims.extracted`` event in Stage 6, not at ingestion time): a parsed doc's extraction is
treated as one episode, summarized into a MemCell bound to its claims/spans, written, and
logged with an append-only ``create`` patch. Persisting the cell is necessary because the
returned patch references it only by id; applying the patch records the revision so the
memory log is uniform across create/supersede/retract.

Multi-cell-per-document clustering (one batch yielding several episodes) is an open question
the plan defers — :class:`~metis_maintainer.memory.scene.SceneBuilder` already clusters cells,
and the builder primitive can be re-pointed at sub-document clusters once the eval justifies it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis_maintainer.memory.memcell import MemCellBuilder
from metis_maintainer.memory.supersession import create_patch
from metis_protocol import ExtractionBatch, MemoryPatch, MemoryStore


class MemoryConsolidator:
    def __init__(self, memory_store: MemoryStore, *, builder: MemCellBuilder | None = None) -> None:
        self._store = memory_store
        self._builder = builder if builder is not None else MemCellBuilder()

    async def consolidate(self, batch: ExtractionBatch) -> MemoryPatch:
        if not batch.claims and not batch.events:
            raise ValueError("cannot consolidate an empty extraction batch")
        cell = await self._builder.build(
            workspace_id=batch.workspace_id, claims=batch.claims, events=batch.events
        )
        await self._store.write_mem_cell(cell)
        patch = create_patch(cell)
        await self._store.apply_patch(patch)  # append-only record of the creation
        return patch


if TYPE_CHECKING:
    from metis_protocol import Consolidator

    def _conforms(consolidator: MemoryConsolidator) -> Consolidator:
        return consolidator  # static proof MemoryConsolidator satisfies the protocol
