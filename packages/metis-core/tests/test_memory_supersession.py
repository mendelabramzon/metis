"""Superseding a mem cell hides it from queries but keeps it auditable."""

from metis_core.stores import PostgresMemoryStore
from metis_protocol import MemoryScope
from metis_protocol.examples import WS, mem_cell, memory_patch


async def test_supersede_hides_from_queries_but_keeps_cell(sessionmaker):
    store = PostgresMemoryStore(sessionmaker)
    cell = mem_cell()
    await store.write_mem_cell(cell)

    before = await store.query_cells(MemoryScope(workspace_id=WS))
    assert any(c.id == cell.id for c in before)

    # memory_patch() supersedes mem_cell() (same target id).
    await store.apply_patch(memory_patch())

    after = await store.query_cells(MemoryScope(workspace_id=WS))
    assert all(c.id != cell.id for c in after)  # excluded from default queries
    assert (
        await store.get_mem_cell(cell.id) is not None
    )  # superseded, not retracted: still auditable
