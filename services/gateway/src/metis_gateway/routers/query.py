"""Query/chat: run the agent loop and return a grounded answer with flat citations.

Sensitivity is bound by the caller's scope (``principal.max_sensitivity``), so the answer can only
rest on evidence the requester is allowed to see — enforced before retrieval, not after.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, UserDep
from metis_gateway.schemas import Citation, DisagreementView, QueryRequestBody, QueryResponse
from metis_runtime.agent import AgentRequest

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def query(body: QueryRequestBody, backend: BackendDep, principal: UserDep) -> QueryResponse:
    run = await backend.agent.run(
        AgentRequest(
            workspace_id=backend.workspace_id,
            instruction=body.text,
            max_sensitivity=principal.max_sensitivity,
            top_k=body.top_k,
        )
    )
    answer = run.answer
    citations: list[Citation] = []
    if answer is not None:
        rows = await backend.workspace.citation_rows(answer.claims)
        citations = [
            Citation(
                claim_id=claim_id,
                source_span_id=span_id,
                artifact_id=artifact_id,
                sensitivity=sensitivity,
            )
            for claim_id, span_id, artifact_id, sensitivity in rows
        ]
    return QueryResponse(
        run_id=str(run.run_id),
        status=run.status.value,
        answer=answer.text if answer is not None else run.summary,
        sufficient=answer.sufficient if answer is not None else False,
        citations=citations,
        contradictions=list(answer.contradictions) if answer is not None else [],
        disagreements=(
            [DisagreementView.from_conflict(c) for c in answer.conflicts]
            if answer is not None
            else []
        ),
        filebacks=len(run.filebacks),
        pending_approvals=[request.key for request in run.pending_approvals],
    )
