"""Consolidation persists a MemCell; superseding hides it from queries but keeps it auditable.

End-to-end against the real store, so it also proves the maintainer's patch builders drive
the store's append-only supersede/retract semantics correctly.
"""

from metis_core.stores import PostgresMemoryStore
from metis_maintainer.memory import (
    MemCellBuilder,
    MemoryConsolidator,
    mark_supersedes,
    retract_patch,
    supersede_patch,
)
from metis_protocol import MemCellId, MemoryOp, MemoryScope
from metis_protocol.examples import CLM2, WS, claim, extraction_batch


async def test_consolidate_then_supersede_then_retract(sessionmaker) -> None:
    store = PostgresMemoryStore(sessionmaker)

    # Consolidate an extraction batch into a persisted MemCell + a CREATE patch.
    patch = await MemoryConsolidator(store).consolidate(extraction_batch())
    assert patch.op is MemoryOp.CREATE
    old_id = MemCellId(patch.target_id)
    assert await store.get_mem_cell(old_id) is not None

    # A newer cell supersedes it (corrected role).
    newer = await MemCellBuilder().build(
        workspace_id=WS,
        claims=[claim().model_copy(update={"id": CLM2, "text": "Ada is the CEO of Acme."})],
    )
    newer = mark_supersedes(newer, old_id)
    await store.write_mem_cell(newer)
    await store.apply_patch(supersede_patch(superseded_id=old_id, by_cell=newer))

    live = await store.query_cells(MemoryScope(workspace_id=WS))
    assert all(cell.id != old_id for cell in live)  # superseded -> excluded from queries
    assert await store.get_mem_cell(old_id) is not None  # ...but still auditable
    assert newer.supersedes is not None
    assert newer.supersedes.mem_cell_id == old_id

    # Retracting the newer cell hides it from get(), too.
    await store.apply_patch(retract_patch(cell=newer, reason="test"))
    assert await store.get_mem_cell(newer.id) is None
