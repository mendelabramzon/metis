"""An injected contradiction is detected and surfaced, citing the conflicting claims."""

from metis_maintainer.jobs import DetectContradictionsJob
from metis_protocol import BatchId, ExtractionBatch, MemoryScope, new_id
from metis_protocol.examples import CLM1, CLM2, PDOC, PROV, WS, claim


def _conflicting_batch() -> ExtractionBatch:
    # Same subject (Ada) and predicate (role_of), two different values -> a contradiction.
    ada_cto = claim()
    ada_ceo = claim().model_copy(update={"id": CLM2, "text": "Ada is the CEO of Acme."})
    return ExtractionBatch(
        id=new_id(BatchId),
        workspace_id=WS,
        parsed_doc_id=PDOC,
        provenance=PROV,
        claims=(ada_cto, ada_ceo),
    )


async def test_injected_contradiction_is_detected(deps) -> None:
    await deps.claim_store.write(_conflicting_batch())

    outcome = await DetectContradictionsJob().run(deps, {"workspace_id": str(WS)})
    assert outcome.counts["contradictions"] >= 1

    found = await deps.memory_store.query_contradictions(MemoryScope(workspace_id=WS))
    assert found, "the contradiction should be surfaced (written), not merged away"
    cited = {str(ref.claim_id) for contradiction in found for ref in contradiction.claims}
    assert {str(CLM1), str(CLM2)} <= cited
