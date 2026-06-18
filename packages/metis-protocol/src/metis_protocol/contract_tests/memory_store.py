"""Abstract contract suite for :class:`~metis_protocol.interfaces.MemoryStore`."""

from __future__ import annotations

import pytest

from metis_protocol.enums import MemoryOp
from metis_protocol.examples import (
    WS,
    contradiction,
    foresight,
    mem_cell,
    mem_scene,
    memory_patch,
    profile,
)
from metis_protocol.interfaces import MemoryStore
from metis_protocol.query import MemoryScope


class MemoryStoreContract:
    @pytest.fixture
    def memory_store(self) -> MemoryStore:
        raise NotImplementedError

    async def test_write_then_get_mem_cell(self, memory_store: MemoryStore) -> None:
        cell = mem_cell()
        assert await memory_store.write_mem_cell(cell) == cell.id
        assert await memory_store.get_mem_cell(cell.id) == cell

    async def test_write_then_get_scene(self, memory_store: MemoryStore) -> None:
        scene = mem_scene()
        assert await memory_store.write_scene(scene) == scene.id
        assert await memory_store.get_scene(scene.id) == scene

    async def test_retract_patch_removes_cell(self, memory_store: MemoryStore) -> None:
        cell = mem_cell()
        await memory_store.write_mem_cell(cell)
        patch = memory_patch().model_copy(
            update={"op": MemoryOp.RETRACT, "target_id": str(cell.id)}
        )
        await memory_store.apply_patch(patch)
        assert await memory_store.get_mem_cell(cell.id) is None

    async def test_query_cells_returns_written(self, memory_store: MemoryStore) -> None:
        cell = mem_cell()
        await memory_store.write_mem_cell(cell)
        cells = await memory_store.query_cells(MemoryScope(workspace_id=WS))
        assert cell in cells

    async def test_write_then_get_profile(self, memory_store: MemoryStore) -> None:
        prof = profile()
        assert await memory_store.write_profile(prof) == prof.id
        assert await memory_store.get_profile(prof.id) == prof

    async def test_profile_write_is_upsert(self, memory_store: MemoryStore) -> None:
        prof = profile()
        await memory_store.write_profile(prof)
        revised = prof.model_copy(update={"label": "Acme (revised)"})
        await memory_store.write_profile(revised)  # same id -> replaces, not forks
        stored = await memory_store.get_profile(prof.id)
        assert stored is not None
        assert stored.label == "Acme (revised)"

    async def test_write_contradiction_then_query(self, memory_store: MemoryStore) -> None:
        ctr = contradiction()
        assert await memory_store.write_contradiction(ctr) == ctr.id
        found = await memory_store.query_contradictions(MemoryScope(workspace_id=WS))
        assert ctr in found

    async def test_write_foresight_then_query(self, memory_store: MemoryStore) -> None:
        fst = foresight()
        assert await memory_store.write_foresight(fst) == fst.id
        found = await memory_store.query_foresights(MemoryScope(workspace_id=WS))
        assert fst in found
