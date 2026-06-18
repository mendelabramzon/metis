"""Propose filing a useful answer back into memory/wiki — as a proposal, never a direct write.

File-back is a trust boundary: the runtime answers, it does not mutate the substrate. So this
returns a *proposal* (claim-cited) that the maintainer/approval flow (Stage 6/7/12) can turn into
a patch. Only sufficient, grounded answers are worth filing back; uncertainty answers yield none.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_protocol import ClaimRef, QueryRequest, SourceSpanRef
from metis_runtime.query.answer import Answer


@dataclass(frozen=True)
class FilebackProposal:
    kind: str  # "memory" or "wiki" — which substrate this would file back into
    summary: str
    claims: tuple[ClaimRef, ...]
    source_spans: tuple[SourceSpanRef, ...]


def propose_fileback(
    query: QueryRequest, answer: Answer, *, kind: str = "memory"
) -> FilebackProposal | None:
    if not answer.sufficient or not answer.claims:
        return None  # nothing grounded enough to file back
    return FilebackProposal(
        kind=kind,
        summary=f"Q: {query.text}",
        claims=answer.claims,
        source_spans=answer.source_spans,
    )
