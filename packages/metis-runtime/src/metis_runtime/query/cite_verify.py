"""Citation verification: every claim an answer cites must map to retrieved evidence.

This is the groundedness gate measured separately from answer prose: an answer is grounded iff
each cited claim ref appears in the EvidenceSet that was retrieved for the query. Any claim not
in the evidence is flagged as uncited so the pipeline can surface it rather than pass off an
unsupported assertion.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_protocol import ClaimRef, EvidenceSet
from metis_runtime.query.answer import Answer


@dataclass(frozen=True)
class CitationCheck:
    grounded: bool
    uncited: tuple[ClaimRef, ...]


def verify_citations(answer: Answer, evidence: EvidenceSet) -> CitationCheck:
    allowed = {str(ref.claim_id) for ref in evidence.claims}
    uncited = tuple(ref for ref in answer.claims if str(ref.claim_id) not in allowed)
    return CitationCheck(grounded=not uncited, uncited=uncited)
