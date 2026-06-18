"""Revising an episode supersedes the prior cell, which stays auditable."""

from metis_maintainer.jobs import ReviseEpisodesJob
from metis_protocol import BatchId, ExtractionBatch, MemoryScope, new_id
from metis_protocol.examples import ART, CLM2, PDOC, PROV, WS, claim


async def test_revise_supersedes_old_cell_but_keeps_it_auditable(deps) -> None:
    # The claim store has two claims from the same artifact; the seeded cell only knew the first.
    extra = claim().model_copy(update={"id": CLM2, "text": "Ada now reports to the board."})
    await deps.claim_store.write(
        ExtractionBatch(
            id=new_id(BatchId),
            workspace_id=WS,
            parsed_doc_id=PDOC,
            provenance=PROV,
            claims=(claim(), extra),
        )
    )
    old_cell = await deps.memcell_builder.build(workspace_id=WS, claims=[claim()])
    await deps.memory_store.write_mem_cell(old_cell)

    outcome = await ReviseEpisodesJob().run(
        deps, {"workspace_id": str(WS), "artifact_id": str(ART)}
    )
    assert outcome.counts["revised"] == 1

    live = await deps.memory_store.query_cells(MemoryScope(workspace_id=WS))
    assert all(cell.id != old_cell.id for cell in live)  # superseded -> hidden from queries
    assert await deps.memory_store.get_mem_cell(old_cell.id) is not None  # ...still auditable
    current = next(cell for cell in live if cell.id != old_cell.id)
    assert len(current.claims) == 2  # the revised episode incorporates the new claim


async def test_revise_is_idempotent(deps) -> None:
    extra = claim().model_copy(update={"id": CLM2, "text": "Ada now reports to the board."})
    await deps.claim_store.write(
        ExtractionBatch(
            id=new_id(BatchId),
            workspace_id=WS,
            parsed_doc_id=PDOC,
            provenance=PROV,
            claims=(claim(), extra),
        )
    )
    await deps.memory_store.write_mem_cell(
        await deps.memcell_builder.build(workspace_id=WS, claims=[claim()])
    )
    payload = {"workspace_id": str(WS), "artifact_id": str(ART)}
    assert (await ReviseEpisodesJob().run(deps, payload)).counts["revised"] == 1
    assert (await ReviseEpisodesJob().run(deps, payload)).counts["revised"] == 0  # nothing left
