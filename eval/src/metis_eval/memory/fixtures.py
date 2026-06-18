"""A small golden workspace for the memory-vs-naive-RAG comparison.

Each document is a few short facts. Every fact becomes both a *chunk* (a Segment, the unit
naive RAG retrieves) and a *claim* (the unit a MemCell is consolidated from). The golden
questions deliberately need **more than one fact from the same document** to answer — the
exact case consolidation is meant to win: one MemCell carries the whole document's evidence,
while any single chunk carries only a fraction.

Stage 13 will grow this into the full golden-workspace fixture; here it is just enough to
make the headline metric measurable and regression-safe.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from metis_protocol import (
    AgentKind,
    ArtifactId,
    ArtifactKind,
    Attribution,
    Claim,
    ClaimId,
    DocId,
    NormalizedDoc,
    ParsedDoc,
    ParsedDocId,
    PolicyState,
    PrefixedId,
    Provenance,
    RawArtifact,
    Segment,
    SegmentId,
    SegmentKind,
    Sensitivity,
    SourceSpanId,
    SourceSpanRef,
    WorkspaceId,
)

_T = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

# Documents as tuples of atomic facts. Fact index is used in the question key below.
_DOCS: tuple[tuple[str, ...], ...] = (
    (
        "Ada Lovelace joined Acme in January 2026.",
        "Ada was promoted to Chief Technology Officer at Acme.",
        "Acme is headquartered in Geneva.",
    ),
    (
        "Grace Hopper was hired by Acme in March 2025.",
        "Grace leads the Acme compiler team.",
        "Acme released a new database product this year.",
    ),
)


@dataclass(frozen=True)
class GoldenQuestion:
    """A question, the document that answers it, and which facts are jointly required."""

    query: str
    doc_index: int
    fact_indices: tuple[int, ...]


_QUESTIONS: tuple[GoldenQuestion, ...] = (
    GoldenQuestion("When did Ada become Acme's Chief Technology Officer?", 0, (0, 1)),
    GoldenQuestion("What does Grace Hopper do at Acme and when did she join?", 1, (0, 1)),
)


@dataclass(frozen=True)
class Corpus:
    """Everything the comparison needs: evidence rows to load, plus the golden scoring maps."""

    workspace_id: WorkspaceId
    raw_artifacts: tuple[RawArtifact, ...]
    normalized_docs: tuple[NormalizedDoc, ...]
    parsed_docs: tuple[ParsedDoc, ...]
    segments: tuple[Segment, ...]
    doc_claims: dict[int, tuple[Claim, ...]]
    seg_to_span: dict[str, str]  # segment id -> the source span it covers
    questions: tuple[GoldenQuestion, ...]
    expected_spans: dict[str, frozenset[str]]  # question text -> the spans that answer it


def _sid[IdT: PrefixedId](id_type: type[IdT], *parts: str) -> IdT:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:32]
    return id_type(f"{id_type.prefix}_{digest}")


def golden_workspace() -> Corpus:
    workspace_id = _sid(WorkspaceId, "metis-eval", "memory")
    policy = PolicyState(sensitivity=Sensitivity.INTERNAL)
    provenance = Provenance(
        workspace_id=workspace_id,
        attribution=Attribution(agent_kind=AgentKind.CONNECTOR, agent="eval-fixture"),
        received_at=_T,
    )

    def envelope(identifier: PrefixedId) -> dict[str, object]:
        return {"id": identifier, "provenance": provenance, "policy": policy, "created_at": _T}

    raws: list[RawArtifact] = []
    norms: list[NormalizedDoc] = []
    parseds: list[ParsedDoc] = []
    segments: list[Segment] = []
    doc_claims: dict[int, tuple[Claim, ...]] = {}
    seg_to_span: dict[str, str] = {}
    span_of: dict[tuple[int, int], str] = {}

    for doc_index, facts in enumerate(_DOCS):
        artifact_id = _sid(ArtifactId, "art", str(doc_index))
        doc_id = _sid(DocId, "doc", str(doc_index))
        parsed_id = _sid(ParsedDocId, "pdoc", str(doc_index))
        text = "\n".join(facts)
        raws.append(
            RawArtifact(
                **envelope(artifact_id),
                kind=ArtifactKind.FILE,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                media_type="text/plain",
                byte_size=len(text.encode("utf-8")),
                storage_ref=f"raw/eval/{doc_index}.txt",
                filename=f"doc{doc_index}.txt",
            )
        )
        norms.append(
            NormalizedDoc(
                **envelope(doc_id), artifact_id=artifact_id, media_type="text/plain", text=text
            )
        )

        claims: list[Claim] = []
        segment_ids: list[SegmentId] = []
        offset = 0
        for fact_index, fact in enumerate(facts):
            segment_id = _sid(SegmentId, "seg", str(doc_index), str(fact_index))
            span_id = _sid(SourceSpanId, "span", str(doc_index), str(fact_index))
            start, end = offset, offset + len(fact)
            offset = end + 1  # account for the joining newline
            segments.append(
                Segment(
                    **envelope(segment_id),
                    parsed_doc_id=parsed_id,
                    doc_id=doc_id,
                    kind=SegmentKind.PARAGRAPH,
                    order=fact_index,
                    text=fact,
                    char_start=start,
                    char_end=end,
                )
            )
            segment_ids.append(segment_id)
            seg_to_span[str(segment_id)] = str(span_id)
            span_of[(doc_index, fact_index)] = str(span_id)
            claims.append(
                Claim(
                    **envelope(_sid(ClaimId, "clm", str(doc_index), str(fact_index))),
                    text=fact,
                    source_spans=(
                        SourceSpanRef(
                            source_span_id=span_id, artifact_id=artifact_id, doc_id=doc_id
                        ),
                    ),
                    confidence=0.9,
                )
            )
        parseds.append(
            ParsedDoc(**envelope(parsed_id), doc_id=doc_id, segment_ids=tuple(segment_ids))
        )
        doc_claims[doc_index] = tuple(claims)

    expected = {
        question.query: frozenset(
            span_of[(question.doc_index, fact_index)] for fact_index in question.fact_indices
        )
        for question in _QUESTIONS
    }
    return Corpus(
        workspace_id=workspace_id,
        raw_artifacts=tuple(raws),
        normalized_docs=tuple(norms),
        parsed_docs=tuple(parseds),
        segments=tuple(segments),
        doc_claims=doc_claims,
        seg_to_span=seg_to_span,
        questions=_QUESTIONS,
        expected_spans=expected,
    )
