"""Adding a MemCell updates the relevant scene summary without a full recompute."""

from metis_maintainer.memory import SceneBuilder
from metis_protocol import ClaimRef, MemCell, MemCellId
from metis_protocol.examples import CLM1, CLM2, mem_cell


def _cell(n: int, summary: str, claim: ClaimRef) -> MemCell:
    return mem_cell().model_copy(
        update={
            "id": MemCellId("mc_" + format(n, "032x")),
            "summary": summary,
            "content": summary,
            "claims": (claim,),
        }
    )


async def test_add_cell_folds_new_cell_into_existing_scene() -> None:
    builder = SceneBuilder()  # deterministic rollup
    cell_a = _cell(1, "Ada became Acme's CTO in 2026.", ClaimRef(claim_id=CLM1))
    cell_b = _cell(2, "Grace was appointed Acme's CFO.", ClaimRef(claim_id=CLM2))

    scene = await builder.build([cell_a])
    assert {ref.mem_cell_id for ref in scene.mem_cells} == {cell_a.id}

    updated = await builder.add_cell(scene, cell_b)

    # Same scene identity, now covering both cells, with both summaries folded in.
    assert updated.id == scene.id
    assert {ref.mem_cell_id for ref in updated.mem_cells} == {cell_a.id, cell_b.id}
    assert cell_a.summary in updated.summary  # the prior rollup was preserved...
    assert cell_b.summary in updated.summary  # ...and the new cell incorporated
    assert {ref.claim_id for ref in updated.claims} == {CLM1, CLM2}


async def test_add_cell_is_idempotent_for_an_existing_member() -> None:
    builder = SceneBuilder()
    cell = _cell(1, "Ada became Acme's CTO in 2026.", ClaimRef(claim_id=CLM1))
    scene = await builder.build([cell])
    assert await builder.add_cell(scene, cell) == scene  # already a member -> unchanged


async def test_cluster_groups_cells_sharing_a_claim() -> None:
    builder = SceneBuilder()
    a = _cell(1, "Ada joined.", ClaimRef(claim_id=CLM1))
    b = _cell(2, "Ada promoted.", ClaimRef(claim_id=CLM1))  # shares CLM1 with a
    c = _cell(3, "Unrelated note.", ClaimRef(claim_id=CLM2))
    clusters = builder.cluster([a, b, c])
    sizes = sorted(len(group) for group in clusters)
    assert sizes == [1, 2]  # {a, b} cluster via shared claim; {c} on its own
