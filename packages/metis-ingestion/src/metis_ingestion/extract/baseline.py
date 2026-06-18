"""Deterministic baseline extractor: claims, entities, and events with source spans.

No LLM is called, so ingestion tests are reproducible: claims are sentence-level,
entities are proper-noun candidates, events are sentences mentioning a year. Every
produced claim cites at least one source span (the citation invariant). The
``model_provider`` parameter is the seam the Stage 4 router fills in.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from metis_ingestion._build import make_provenance, now_utc, stable_id
from metis_ingestion.spans import make_source_span, span_ref
from metis_protocol import (
    AgentKind,
    BatchId,
    Claim,
    ClaimId,
    Entity,
    EntityId,
    EntityKind,
    Event,
    EventId,
    ExtractionBatch,
    ModelProvider,
    NormalizedDoc,
    ParsedDocId,
    PolicyState,
    Provenance,
    Segment,
    SourceSpan,
    SourceSpanRef,
    WorkspaceId,
)

_PROPER_NOUN = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_ORG_SUFFIX = re.compile(r"\b(?:Inc|LLC|Ltd|Corp|Company|GmbH|Group)\b")
_STOPWORDS = frozenset(
    {
        "The",
        "A",
        "An",
        "This",
        "That",
        "These",
        "Those",
        "It",
        "In",
        "On",
        "At",
        "For",
        "And",
        "But",
        "Or",
        "If",
        "When",
        "While",
        "We",
        "I",
        "You",
        "They",
    }
)


@dataclass(frozen=True)
class ExtractionResult:
    batch: ExtractionBatch
    source_spans: tuple[SourceSpan, ...]


def _iter_sentences(text: str, base: int) -> Iterator[tuple[str, int, int]]:
    """Yield ``(sentence, abs_start, abs_end)`` with offsets relative to ``base``."""
    position = 0
    length = len(text)
    while position < length:
        while position < length and text[position].isspace():
            position += 1
        if position >= length:
            break
        start = position
        while position < length:
            char = text[position]
            if char in ".!?" and (position + 1 >= length or text[position + 1].isspace()):
                position += 1
                break
            if char == "\n":
                break
            position += 1
        sentence = text[start:position].rstrip()
        if sentence:
            yield sentence, base + start, base + start + len(sentence)


def _proper_nouns(sentence: str) -> list[str]:
    names: list[str] = []
    for match in _PROPER_NOUN.finditer(sentence):
        name = match.group(0)
        if " " not in name and name in _STOPWORDS:
            continue
        names.append(name)
    return names


class BaselineExtractor:
    def __init__(self, *, model_provider: ModelProvider | None = None) -> None:
        self._model_provider = model_provider  # Stage 4 seam; unused by the baseline

    def extract(
        self,
        doc: NormalizedDoc,
        parsed_doc_id: ParsedDocId,
        segments: Sequence[Segment],
    ) -> ExtractionResult:
        workspace_id = doc.provenance.workspace_id
        policy = doc.policy
        provenance = make_provenance(
            workspace_id,
            agent_kind=AgentKind.EXTRACTOR,
            agent="baseline",
            operation="extract_claims",
            inputs=(str(parsed_doc_id),),
        )

        spans: dict[str, SourceSpan] = {}
        claims: list[Claim] = []
        entities: dict[str, Entity] = {}
        events: list[Event] = []

        for segment in segments:
            for sentence, start, end in _iter_sentences(segment.text, segment.char_start):
                span = make_source_span(
                    artifact_id=doc.artifact_id, doc_id=doc.id, char_start=start, char_end=end
                )
                spans[str(span.id)] = span
                ref = span_ref(span)
                claims.append(
                    self._claim(workspace_id, doc, policy, provenance, sentence, span, ref)
                )
                for name in _proper_nouns(sentence):
                    if name not in entities:
                        entities[name] = self._entity(workspace_id, policy, provenance, name, ref)
                if _YEAR.search(sentence):
                    events.append(self._event(doc, policy, provenance, sentence, span, ref))

        batch = ExtractionBatch(
            id=stable_id(BatchId, str(parsed_doc_id)),
            workspace_id=workspace_id,
            parsed_doc_id=parsed_doc_id,
            provenance=provenance,
            claims=tuple(claims),
            entities=tuple(entities.values()),
            events=tuple(events),
        )
        return ExtractionResult(batch=batch, source_spans=tuple(spans.values()))

    def _claim(
        self,
        workspace_id: WorkspaceId,
        doc: NormalizedDoc,
        policy: PolicyState,
        provenance: Provenance,
        text: str,
        span: SourceSpan,
        ref: SourceSpanRef,
    ) -> Claim:
        return Claim(
            id=stable_id(
                ClaimId,
                f"{workspace_id}:{doc.artifact_id}:{span.char_start}:{span.char_end}:{text}",
            ),
            provenance=provenance,
            policy=policy,
            created_at=now_utc(),
            text=text,
            source_spans=(ref,),
            confidence=0.5,
        )

    def _entity(
        self,
        workspace_id: WorkspaceId,
        policy: PolicyState,
        provenance: Provenance,
        name: str,
        ref: SourceSpanRef,
    ) -> Entity:
        kind = EntityKind.ORGANIZATION if _ORG_SUFFIX.search(name) else EntityKind.OTHER
        return Entity(
            id=stable_id(EntityId, f"{workspace_id}:{kind.value}:{name}"),
            provenance=provenance,
            policy=policy,
            created_at=now_utc(),
            kind=kind,
            name=name,
            source_spans=(ref,),
        )

    def _event(
        self,
        doc: NormalizedDoc,
        policy: PolicyState,
        provenance: Provenance,
        text: str,
        span: SourceSpan,
        ref: SourceSpanRef,
    ) -> Event:
        return Event(
            id=stable_id(EventId, f"{doc.artifact_id}:{span.char_start}:{span.char_end}:{text}"),
            provenance=provenance,
            policy=policy,
            created_at=now_utc(),
            summary=text,
            source_spans=(ref,),
        )
