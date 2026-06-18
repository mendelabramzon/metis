"""Insufficient evidence yields an uncertainty answer, not a confident fabrication."""

from metis_protocol import (
    ClaimRef,
    ContextBundle,
    ContextBundleId,
    ContextSection,
    QueryId,
    QueryRequest,
    new_id,
)
from metis_protocol.examples import CLM1, WS
from metis_runtime.query import assess_sufficiency


def test_empty_context_is_insufficient() -> None:
    bundle = ContextBundle(id=new_id(ContextBundleId), query_id=new_id(QueryId), sections=())
    assert not assess_sufficiency(bundle).sufficient


def test_claim_cited_section_is_sufficient() -> None:
    section = ContextSection(text="Ada is the CTO.", claims=(ClaimRef(claim_id=CLM1),))
    bundle = ContextBundle(
        id=new_id(ContextBundleId), query_id=new_id(QueryId), sections=(section,)
    )
    assert assess_sufficiency(bundle).sufficient


async def test_query_with_no_evidence_returns_uncertainty(query_engine) -> None:
    query = QueryRequest(id=new_id(QueryId), workspace_id=WS, text="What is the capital of France?")
    answer = await query_engine.answer(query)
    assert not answer.sufficient
    assert answer.claims == ()  # no fabricated citations
    assert "enough" in answer.text.lower()
