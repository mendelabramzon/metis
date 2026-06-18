"""Reference in-memory store implementations.

These are the simplest possible conforming implementations of the store
interfaces. They exist to self-test the abstract contract suites (so the suites
are proven usable before ``metis-core`` consumes them) and as throwaway fakes for
downstream unit tests. They are not production stores.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from metis_protocol.artifacts import RawArtifact
from metis_protocol.claims import Claim, ClaimWriteResult, Entity, Event, ExtractionBatch
from metis_protocol.enums import MemoryOp
from metis_protocol.ids import (
    ArtifactId,
    ClaimId,
    EntityId,
    EventId,
    MemCellId,
    MemSceneId,
)
from metis_protocol.memory import MemCell, MemoryPatch, MemScene
from metis_protocol.query import ClaimFilter, MemoryScope
from metis_protocol.refs import ArtifactRef


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._by_id: dict[ArtifactId, RawArtifact] = {}
        self._by_hash: dict[str, ArtifactId] = {}

    async def put(self, raw: RawArtifact) -> ArtifactRef:
        existing = self._by_hash.get(raw.content_hash)
        if existing is not None:  # idempotent by content hash
            return ArtifactRef(artifact_id=existing)
        self._by_id[raw.id] = raw
        self._by_hash[raw.content_hash] = raw.id
        return ArtifactRef(artifact_id=raw.id)

    async def get(self, ref: ArtifactRef) -> RawArtifact | None:
        return self._by_id.get(ref.artifact_id)


class InMemoryClaimStore:
    def __init__(self) -> None:
        self._claims: dict[ClaimId, Claim] = {}
        self._entities: dict[EntityId, Entity] = {}
        self._events: dict[EventId, Event] = {}

    async def write(self, batch: ExtractionBatch) -> ClaimWriteResult:
        new_claims: list[ClaimId] = []
        new_entities: list[EntityId] = []
        new_events: list[EventId] = []
        skipped = 0
        for claim in batch.claims:
            if claim.id in self._claims:
                skipped += 1
            else:
                self._claims[claim.id] = claim
                new_claims.append(claim.id)
        for ent in batch.entities:
            if ent.id not in self._entities:
                self._entities[ent.id] = ent
                new_entities.append(ent.id)
        for evt in batch.events:
            if evt.id not in self._events:
                self._events[evt.id] = evt
                new_events.append(evt.id)
        return ClaimWriteResult(
            written_claims=tuple(new_claims),
            written_entities=tuple(new_entities),
            written_events=tuple(new_events),
            skipped=skipped,
        )

    async def query(self, claim_filter: ClaimFilter) -> Sequence[Claim]:
        out = list(self._claims.values())
        if claim_filter.predicate is not None:
            out = [c for c in out if c.predicate == claim_filter.predicate]
        if claim_filter.text_contains is not None:
            out = [c for c in out if claim_filter.text_contains in c.text]
        if claim_filter.entity is not None:
            out = [c for c in out if claim_filter.entity in (c.subject_ref, c.object_ref)]
        if claim_filter.limit is not None:
            out = out[: claim_filter.limit]
        return out

    async def get(self, claim_id: ClaimId) -> Claim | None:
        return self._claims.get(claim_id)


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._cells: dict[MemCellId, MemCell] = {}
        self._scenes: dict[MemSceneId, MemScene] = {}
        self._patches: list[MemoryPatch] = []

    async def write_mem_cell(self, cell: MemCell) -> MemCellId:
        self._cells[cell.id] = cell
        return cell.id

    async def get_mem_cell(self, mem_cell_id: MemCellId) -> MemCell | None:
        return self._cells.get(mem_cell_id)

    async def write_scene(self, scene: MemScene) -> MemSceneId:
        self._scenes[scene.id] = scene
        return scene.id

    async def get_scene(self, mem_scene_id: MemSceneId) -> MemScene | None:
        return self._scenes.get(mem_scene_id)

    async def apply_patch(self, patch: MemoryPatch) -> None:
        self._patches.append(patch)
        if patch.op is MemoryOp.RETRACT:
            self._cells.pop(MemCellId(patch.target_id), None)

    async def query_cells(self, scope: MemoryScope) -> Sequence[MemCell]:
        cells = list(self._cells.values())
        if scope.since is not None:
            cells = [c for c in cells if c.occurred_at is None or c.occurred_at >= scope.since]
        if scope.until is not None:
            cells = [c for c in cells if c.occurred_at is None or c.occurred_at <= scope.until]
        return cells


if TYPE_CHECKING:
    # Static proof that the fakes satisfy the structural store interfaces.
    from metis_protocol.interfaces import ArtifactStore, ClaimStore, MemoryStore

    _artifact_store: ArtifactStore = InMemoryArtifactStore()
    _claim_store: ClaimStore = InMemoryClaimStore()
    _memory_store: MemoryStore = InMemoryMemoryStore()
