"""Abstract contract suite for :class:`~metis_protocol.interfaces.MemoryStore`."""

from __future__ import annotations

import pytest

from metis_protocol.enums import MemoryOp
from metis_protocol.examples import WS, mem_cell, mem_scene, memory_patch
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
