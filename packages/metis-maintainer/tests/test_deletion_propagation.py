"""Deleting an artifact propagates the tombstone into derived claims and mem cells."""

from metis_maintainer.jobs import ValidateDeletionsJob
from metis_protocol import BatchId, ExtractionBatch, new_id
from metis_protocol.examples import ART, PDOC, PROV, WS, claim


async def test_deletion_propagates_and_is_consistent(deps) -> None:
    # A claim from artifact ART, and a mem cell built on that claim.
    await deps.claim_store.write(
        ExtractionBatch(
            id=new_id(BatchId),
            workspace_id=WS,
            parsed_doc_id=PDOC,
            provenance=PROV,
            claims=(claim(),),
        )
    )
    cell = await deps.memcell_builder.build(workspace_id=WS, claims=[claim()])
    await deps.memory_store.write_mem_cell(cell)

    outcome = await ValidateDeletionsJob().run(
        deps, {"workspace_id": str(WS), "artifact_id": str(ART)}
    )

    assert outcome.counts["claims"] >= 1  # the claim was tombstoned...
    assert outcome.counts["mem_cells"] >= 1  # ...and so was the cell built on it
    assert outcome.counts["consistent"] == 1  # re-running touches nothing -> fully propagated

    # The derived artifacts are now hidden from default reads.
    assert await deps.claim_store.get(claim().id) is None
    assert await deps.memory_store.get_mem_cell(cell.id) is None
