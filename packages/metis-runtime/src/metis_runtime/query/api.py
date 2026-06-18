"""The query pipeline entrypoint: QueryRequest -> grounded Answer.

Flow: plan -> retrieve -> pack -> verify sufficiency -> (corrective retrieve on a miss) ->
answer -> verify citations. Retrieval already filtered by the requester's sensitivity ceiling
(in the retriever); insufficient evidence yields an uncertainty answer rather than a guess;
contradictions in the evidence are surfaced in the answer; and any answer claim that does not map
to retrieved evidence is flagged. Tool/skill use and the agent loop are Stages 9-10.
"""

from __future__ import annotations

from dataclasses import replace

from metis_core.llm import ModelCaller
from metis_protocol import Claim, ClaimStore, ContextBundle, EvidenceSet, QueryRequest
from metis_runtime.query.answer import Answer, AnswerGenerator
from metis_runtime.query.cite_verify import verify_citations
from metis_runtime.query.pack import BudgetedContextPacker
from metis_runtime.query.plan import plan_query
from metis_runtime.query.retrievers import MemoryRetriever
from metis_runtime.query.rewrite import rewrite_query
from metis_runtime.query.sufficiency import Sufficiency, assess_sufficiency


class QueryEngine:
    def __init__(
        self,
        *,
        retriever: MemoryRetriever,
        claim_store: ClaimStore,
        packer: BudgetedContextPacker | None = None,
        generator: AnswerGenerator | None = None,
        caller: ModelCaller | None = None,
    ) -> None:
        self._retriever = retriever
        self._claims = claim_store
        self._packer = packer if packer is not None else BudgetedContextPacker()
        self._generator = generator if generator is not None else AnswerGenerator(caller=caller)
        self._caller = caller

    async def answer(self, query: QueryRequest) -> Answer:
        plan = plan_query(query)
        if not plan.retrieve:
            return Answer(query_id=query.id, text="Ask me a question about this workspace.")

        scoped = query.model_copy(update={"top_k": plan.top_k})
        evidence, bundle, sufficiency = await self._retrieve_and_pack(scoped)

        if not sufficiency.sufficient:  # corrective retrieval (CRAG): rewrite + retry once
            rewritten = await rewrite_query(
                query.text, workspace_id=query.workspace_id, caller=self._caller
            )
            if rewritten != query.text:
                retry = scoped.model_copy(update={"text": rewritten})
                evidence, bundle, sufficiency = await self._retrieve_and_pack(retry)

        if not sufficiency.sufficient:
            return await self._generator.generate(query, bundle, claims=[], sufficient=False)

        claims = await self._resolve_claims(evidence)
        answer = await self._generator.generate(query, bundle, claims=claims, sufficient=True)
        check = verify_citations(answer, evidence)
        return answer if check.grounded else replace(answer, uncited_claims=check.uncited)

    async def _retrieve_and_pack(
        self, query: QueryRequest
    ) -> tuple[EvidenceSet, ContextBundle, Sufficiency]:
        evidence, cells = await self._retriever.retrieve_cells(query)
        bundle = self._packer.pack(query, evidence, cells={cell.id: cell for cell in cells})
        return evidence, bundle, assess_sufficiency(bundle)

    async def _resolve_claims(self, evidence: EvidenceSet) -> list[Claim]:
        resolved: list[Claim] = []
        for ref in evidence.claims:
            claim = await self._claims.get(ref.claim_id)
            if claim is not None:
                resolved.append(claim)
        return resolved
