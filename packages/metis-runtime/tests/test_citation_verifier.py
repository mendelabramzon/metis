"""An answer is grounded only if every cited claim maps to retrieved evidence."""

from metis_protocol import ClaimRef, EvidenceSet, EvidenceSetId, QueryId, new_id
from metis_protocol.examples import CLM1, CLM2
from metis_runtime.query import Answer, verify_citations


def _evidence(*claim_ids: object) -> EvidenceSet:
    return EvidenceSet(
        id=new_id(EvidenceSetId),
        query_id=new_id(QueryId),
        claims=tuple(ClaimRef(claim_id=cid) for cid in claim_ids),  # type: ignore[arg-type]
    )


def test_answer_citing_only_evidence_is_grounded() -> None:
    answer = Answer(query_id=new_id(QueryId), text="...", claims=(ClaimRef(claim_id=CLM1),))
    check = verify_citations(answer, _evidence(CLM1))
    assert check.grounded
    assert check.uncited == ()


def test_answer_citing_an_unknown_claim_is_flagged() -> None:
    answer = Answer(query_id=new_id(QueryId), text="...", claims=(ClaimRef(claim_id=CLM2),))
    check = verify_citations(answer, _evidence(CLM1))  # CLM2 not in evidence
    assert not check.grounded
    assert any(ref.claim_id == CLM2 for ref in check.uncited)
