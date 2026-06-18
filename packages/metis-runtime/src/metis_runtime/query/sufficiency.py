"""Sufficiency verification: is the packed context enough to answer (Self-RAG / CRAG)?

Deterministic so it neither over-retries (cost) nor silently under-retries (hallucination):
context is sufficient when it has at least one claim-cited section. An insufficient result tells
the pipeline to attempt corrective retrieval, and failing that, to answer with uncertainty
rather than confidently fabricate.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_protocol import ContextBundle


@dataclass(frozen=True)
class Sufficiency:
    sufficient: bool
    score: float
    reason: str


def assess_sufficiency(bundle: ContextBundle, *, min_cited_sections: int = 1) -> Sufficiency:
    cited = [section for section in bundle.sections if section.claims]
    score = len(cited) / len(bundle.sections) if bundle.sections else 0.0
    if len(cited) >= min_cited_sections:
        return Sufficiency(True, round(score, 3), f"{len(cited)} claim-cited section(s)")
    return Sufficiency(False, round(score, 3), "no claim-cited evidence retrieved")
