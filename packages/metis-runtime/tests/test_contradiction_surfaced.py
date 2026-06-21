"""Contradictory evidence is represented explicitly in the answer, not resolved away."""

from metis_protocol import ClaimRef, QueryId, QueryRequest, new_id
from metis_protocol.examples import CLM1, CLM2, WS, claim, mem_cell


async def test_conflicting_evidence_is_surfaced(query_engine, seed) -> None:
    cto = claim()  # CLM1: "Ada is the CTO of Acme." (predicate role_of, subject Ada)
    ceo = claim().model_copy(update={"id": CLM2, "text": "Ada is the CEO of Acme."})
    cell = mem_cell().model_copy(
        update={
            "claims": (ClaimRef(claim_id=CLM1), ClaimRef(claim_id=CLM2)),
            "summary": "Ada's role at Acme.",
            "content": "Ada is the CTO of Acme. Ada is the CEO of Acme.",
        }
    )
    await seed(cell, [cto, ceo])

    query = QueryRequest(id=new_id(QueryId), workspace_id=WS, text="What is Ada's role at Acme?")
    answer = await query_engine.answer(query)

    assert answer.sufficient
    assert answer.contradictions  # the conflict is surfaced...
    assert "onflicting" in answer.text  # ...and shown in the answer text, not resolved away

    # ...and as a structured disagreement (A3): both sides, each backed by a source span.
    assert len(answer.conflicts) == 1
    sides = answer.conflicts[0].sides
    assert {s.text for s in sides} == {"Ada is the CTO of Acme.", "Ada is the CEO of Acme."}
    assert all(s.claim_id and s.source_span_id for s in sides)
