"""A deterministic, in-memory engine over the golden workspace — no Postgres, no LLM, no Docker.

Ingestion runs the *real* Stage 3 ``BaselineExtractor`` (so claims and spans are genuine), and
retrieval/answering are deterministic lexical grounding. It is the ``Answerer`` the Stage 10
``AgentLoop`` calls in the skill-safety dimension. This keeps the small golden-workspace replay
cheap and reproducible enough for CI regression diffs, the whole point of the harness.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_eval.golden import GoldenDoc, GoldenWorkspace
from metis_eval.tokens import terms
from metis_ingestion import (
    BaselineExtractor,
    build_normalized_doc,
    build_raw_artifact,
    get_format,
    mime,
    parse_document,
)
from metis_ingestion.failures import UnsupportedMediaType
from metis_protocol import (
    Claim,
    ClaimRef,
    NormalizedDoc,
    PolicyState,
    QueryId,
    QueryRequest,
    Sensitivity,
    SourceSpan,
    WorkspaceId,
    is_at_least,
    max_sensitivity,
    new_id,
)
from metis_runtime.query import Answer


@dataclass(frozen=True)
class IngestedDoc:
    name: str
    doc: NormalizedDoc
    claims: tuple[Claim, ...]
    spans: dict[str, SourceSpan]
    deleted: bool
    injection: bool


class GoldenEngine:
    def __init__(self, workspace_id: WorkspaceId) -> None:
        self._workspace_id = workspace_id
        self.docs: list[IngestedDoc] = []

    @classmethod
    def load(cls, workspace: GoldenWorkspace) -> GoldenEngine:
        engine = cls(workspace.workspace_id)
        for golden_doc in workspace.documents:
            engine.ingest(golden_doc)
        return engine

    def ingest(self, golden_doc: GoldenDoc) -> IngestedDoc:
        data = golden_doc.text.encode("utf-8")
        media = mime.detect(golden_doc.name, data[:512])
        fmt = get_format(media.media_type)
        if fmt is None:
            raise UnsupportedMediaType(media.media_type)
        policy = PolicyState(
            sensitivity=golden_doc.sensitivity,
            allow_external_models=not is_at_least(golden_doc.sensitivity, Sensitivity.RESTRICTED),
        )
        raw = build_raw_artifact(
            data,
            workspace_id=self._workspace_id,
            filename=golden_doc.name,
            media_info=media,
            policy=policy,
            connector="eval",
        )
        doc = build_normalized_doc(raw, data, policy=policy)
        parsed, segments = parse_document(doc, fmt.segmentation)
        result = BaselineExtractor().extract(doc, parsed.id, segments)
        ingested = IngestedDoc(
            name=golden_doc.name,
            doc=doc,
            claims=result.batch.claims,
            spans={str(span.id): span for span in result.source_spans},
            deleted=golden_doc.deleted,
            injection=golden_doc.injection,
        )
        self.docs.append(ingested)
        return ingested

    def doc(self, name: str) -> IngestedDoc:
        return next(ingested for ingested in self.docs if ingested.name == name)

    def live_claims(self, *, ceiling: Sensitivity = Sensitivity.RESTRICTED) -> list[Claim]:
        """Claims a requester at ``ceiling`` may see (deleted docs + over-ceiling data excluded)."""
        return [
            claim
            for ingested in self.docs
            if not ingested.deleted
            for claim in ingested.claims
            if is_at_least(ceiling, claim.policy.sensitivity)
        ]

    def retrieve(
        self, query_text: str, *, k: int = 3, ceiling: Sensitivity = Sensitivity.INTERNAL
    ) -> list[Claim]:
        wanted = terms(query_text)
        scored = [
            (len(wanted & terms(claim.text)), claim) for claim in self.live_claims(ceiling=ceiling)
        ]
        ranked = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: -pair[0])
        return [claim for _, claim in ranked[:k]]

    async def answer(self, query: QueryRequest) -> Answer:
        hits = self.retrieve(query.text, ceiling=query.max_sensitivity)
        if not hits:
            return Answer(
                query_id=query.id,
                text="I don't have enough grounded evidence to answer that.",
                sufficient=False,
            )
        top = hits[:3]
        return Answer(
            query_id=query.id,
            text="Based on the evidence: " + " ".join(claim.text for claim in top),
            claims=tuple(ClaimRef(claim_id=claim.id) for claim in top),
            source_spans=tuple(ref for claim in top for ref in claim.source_spans),
            sufficient=True,
            sensitivity=max_sensitivity(*(claim.policy.sensitivity for claim in top)),
        )

    def query_request(
        self, text: str, *, ceiling: Sensitivity = Sensitivity.INTERNAL
    ) -> QueryRequest:
        return QueryRequest(
            id=new_id(QueryId),
            workspace_id=self._workspace_id,
            text=text,
            max_sensitivity=ceiling,
        )
