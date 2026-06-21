"""Generate an answer over packed context — grounded, contradiction-aware, uncertainty-honest.

The ``Answer`` is a runtime value (not a protocol artifact): it carries the answer text plus the
exact claim/source-span citations it rests on. Generation has a deterministic, extractive
fallback (so tests need no model) and an optional ``query_answer`` LLM path; either way the
citations come from the retrieved evidence, contradictions among the evidence are surfaced
explicitly, and insufficient evidence yields an honest "not enough evidence" answer rather than a
confident fabrication.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from metis_core.llm import ModelCaller
from metis_protocol import (
    Claim,
    ClaimRef,
    ContextBundle,
    ModelTaskClass,
    QueryId,
    QueryRequest,
    Sensitivity,
    SourceSpanRef,
    max_sensitivity,
)
from metis_runtime.query.prompts import AnswerDraft

_INSUFFICIENT = "I don't have enough grounded evidence in this workspace to answer that."


@dataclass(frozen=True)
class Answer:
    query_id: QueryId
    text: str
    claims: tuple[ClaimRef, ...] = ()
    source_spans: tuple[SourceSpanRef, ...] = ()
    sufficient: bool = True
    contradictions: tuple[str, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    uncited_claims: tuple[ClaimRef, ...] = ()
    sensitivity: Sensitivity = Sensitivity.INTERNAL


@dataclass(frozen=True)
class ConflictSide:
    """One position in a disagreement: a claim and the source span behind it."""

    claim_id: str
    text: str
    source_span_id: str
    artifact_id: str
    sensitivity: Sensitivity


@dataclass(frozen=True)
class Conflict:
    """Same-subject/same-predicate claims that disagree — two or more positions."""

    predicate: str
    sides: tuple[ConflictSide, ...]


def conflicts_among(claims: Sequence[Claim]) -> tuple[Conflict, ...]:
    """Structured disagreements: same-subject/same-predicate claims with differing text."""
    groups: dict[tuple[str, str], list[Claim]] = {}
    for claim in claims:
        if claim.predicate is None:
            continue
        subject = str(claim.subject_ref.entity_id) if claim.subject_ref is not None else ""
        groups.setdefault((subject, claim.predicate), []).append(claim)
    conflicts: list[Conflict] = []
    for (_, predicate), group in groups.items():
        by_text: dict[str, Claim] = {}
        for claim in group:
            by_text.setdefault(claim.text, claim)  # one side per distinct position
        if len(by_text) > 1:
            sides = tuple(_side(by_text[text]) for text in sorted(by_text))
            conflicts.append(Conflict(predicate=predicate, sides=sides))
    return tuple(conflicts)


def _side(claim: Claim) -> ConflictSide:
    span = claim.source_spans[0]  # claims cite >= 1 span (Claim.source_spans min_length=1)
    return ConflictSide(
        claim_id=str(claim.id),
        text=claim.text,
        source_span_id=str(span.source_span_id),
        artifact_id=str(span.artifact_id),
        sensitivity=claim.policy.sensitivity,
    )


def _note(conflict: Conflict) -> str:
    return f"Conflicting '{conflict.predicate}': " + " vs ".join(s.text for s in conflict.sides)


def conflict_notes(claims: Sequence[Claim]) -> tuple[str, ...]:
    """Human-readable notes for same-subject/same-predicate claims that disagree."""
    return tuple(_note(c) for c in conflicts_among(claims))


class AnswerGenerator:
    def __init__(self, *, caller: ModelCaller | None = None) -> None:
        self._caller = caller

    async def generate(
        self,
        query: QueryRequest,
        bundle: ContextBundle,
        *,
        claims: Sequence[Claim],
        sufficient: bool,
    ) -> Answer:
        if not sufficient:
            return Answer(query_id=query.id, text=_INSUFFICIENT, sufficient=False)

        conflicts = conflicts_among(claims)
        contradictions = tuple(_note(c) for c in conflicts)
        cited_claims = tuple(ref for section in bundle.sections for ref in section.claims)
        spans = tuple(ref for section in bundle.sections for ref in section.source_spans)
        text = await self._text(query, bundle, contradictions)
        return Answer(
            query_id=query.id,
            text=text,
            claims=cited_claims,
            source_spans=spans,
            sufficient=True,
            contradictions=contradictions,
            conflicts=conflicts,
            sensitivity=max_sensitivity(*(claim.policy.sensitivity for claim in claims))
            if claims
            else Sensitivity.INTERNAL,
        )

    async def _text(
        self, query: QueryRequest, bundle: ContextBundle, contradictions: Sequence[str]
    ) -> str:
        if self._caller is not None:
            drafted = await self._caller.call_structured(
                task_class=ModelTaskClass.QUERY_ANSWER,
                workspace_id=query.workspace_id,
                user_content=_render_context(query, bundle),
                output_type=AnswerDraft,
                sensitivity=query.max_sensitivity,
            )
            return drafted.answer
        # Deterministic extractive fallback: state the evidence, then surface any conflict.
        lines = ["Based on the workspace evidence:"]
        lines += [f"- {section.text}" for section in bundle.sections]
        if contradictions:
            lines += ["", "Note — conflicting evidence:", *(f"- {note}" for note in contradictions)]
        return "\n".join(lines)


def _render_context(query: QueryRequest, bundle: ContextBundle) -> str:
    blocks = [f"Question: {query.text}", "", "Context:"]
    for section in bundle.sections:
        blocks.append(f"- {section.text}")
    return "\n".join(blocks)
