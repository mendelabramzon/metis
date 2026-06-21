"""Workspaces: list mine, create a shared one, and the membership-gated read/admin endpoints.

``GET /workspaces/{id}`` is the isolation gate in action — a non-member gets 403, which is how one
user's personal workspace stays invisible to another (see ``auth.workspace_context``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from metis_gateway.deps import (
    BackendDep,
    CurrentUserDep,
    MemberDep,
    WorkspaceAdminDep,
    WorkspaceWriterDep,
)
from metis_gateway.errors import NotFoundError, TooManyRequestsError
from metis_gateway.models import over_daily_cap
from metis_gateway.schemas import (
    Citation,
    DisagreementView,
    ErasureView,
    IngestRequest,
    IngestResponse,
    MembershipCreate,
    MembershipView,
    ModelPolicyUpdate,
    ModelPolicyView,
    QueryRequestBody,
    QueryResponse,
    SpendView,
    StarterQuestionsView,
    WorkspaceCreate,
    WorkspaceView,
)
from metis_protocol import (
    MembershipId,
    Role,
    Sensitivity,
    UserId,
    Workspace,
    WorkspaceId,
    WorkspaceMembership,
    WorkspaceModelPolicy,
    is_at_least,
    new_id,
)
from metis_runtime.agent import AgentRequest

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _workspace_view(workspace: Workspace) -> WorkspaceView:
    return WorkspaceView(
        id=str(workspace.id),
        organization_id=str(workspace.organization_id),
        kind=workspace.kind,
        name=workspace.name,
        owner_id=str(workspace.owner_id) if workspace.owner_id is not None else None,
        default_sensitivity=workspace.default_sensitivity,
    )


def _membership_view(membership: WorkspaceMembership) -> MembershipView:
    return MembershipView(
        id=str(membership.id),
        workspace_id=str(membership.workspace_id),
        user_id=str(membership.user_id),
        role=membership.role,
    )


@router.get("", response_model=list[WorkspaceView])
async def my_workspaces(backend: BackendDep, user: CurrentUserDep) -> list[WorkspaceView]:
    return [_workspace_view(w) for w in await backend.identity.workspaces_for_user(user.id)]


@router.post("", response_model=WorkspaceView, status_code=201)
async def create_workspace(
    body: WorkspaceCreate, backend: BackendDep, user: CurrentUserDep
) -> WorkspaceView:
    now = datetime.now(UTC)
    workspace = await backend.identity.create_workspace(
        Workspace(
            id=new_id(WorkspaceId),
            organization_id=user.organization_id,
            kind=body.kind,
            name=body.name,
            owner_id=user.id,
            created_at=now,
        )
    )
    await backend.identity.add_membership(
        WorkspaceMembership(
            id=new_id(MembershipId),
            workspace_id=workspace.id,
            user_id=user.id,
            role=Role.OWNER,
            created_at=now,
        )
    )
    return _workspace_view(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceView)
async def get_workspace(context: MemberDep) -> WorkspaceView:
    return _workspace_view(context.workspace)


@router.get("/{workspace_id}/members", response_model=list[MembershipView])
async def list_members(context: WorkspaceAdminDep, backend: BackendDep) -> list[MembershipView]:
    members = await backend.identity.members_of(context.workspace.id)
    return [_membership_view(m) for m in members]


@router.post("/{workspace_id}/members", response_model=MembershipView, status_code=201)
async def add_member(
    body: MembershipCreate, context: WorkspaceAdminDep, backend: BackendDep
) -> MembershipView:
    target = await backend.identity.get_user(UserId(body.user_id))
    if target is None:
        raise NotFoundError(f"unknown user {body.user_id}")
    membership = await backend.identity.add_membership(
        WorkspaceMembership(
            id=new_id(MembershipId),
            workspace_id=context.workspace.id,
            user_id=target.id,
            role=body.role,
            created_at=datetime.now(UTC),
        )
    )
    return _membership_view(membership)


# --- workspace-scoped engine (ingest + query), routed to that workspace's isolated engine -------


@router.post("/{workspace_id}/ingest", response_model=IngestResponse, status_code=202)
async def ingest_into_workspace(
    body: IngestRequest, context: WorkspaceWriterDep, backend: BackendDep
) -> IngestResponse:
    """Ingest content into the workspace's own engine (writer role required by the gate)."""
    policy = await backend.identity.get_model_policy(context.workspace.id)
    workspace = backend.workspace_for(
        context.workspace.id, allow_external=policy.allow_external_models
    )
    sensitivity = (
        body.sensitivity if body.sensitivity is not None else context.workspace.default_sensitivity
    )
    doc_id, claims = await workspace.ingest(
        filename=body.filename, content=body.content, sensitivity=sensitivity
    )
    return IngestResponse(doc_id=doc_id, artifacts=1, claims=claims)


@router.post("/{workspace_id}/query", response_model=QueryResponse)
async def query_workspace(
    body: QueryRequestBody, context: MemberDep, backend: BackendDep
) -> QueryResponse:
    """Answer against the workspace's own engine (membership required by the gate).

    A member sees the workspace's evidence; intra-workspace sensitivity tiers are a later
    refinement, so the ceiling is the workspace boundary itself. The workspace's model policy
    selects providers (local-only when external is forbidden) and caps daily model spend.
    """
    ws_id = context.workspace.id
    policy = await backend.identity.get_model_policy(ws_id)
    if backend.spend is not None and over_daily_cap(policy, backend.spend.today_total(ws_id)):
        raise TooManyRequestsError("workspace daily model-spend cap reached")
    allow_external = policy.allow_external_models
    run = await backend.agent_for(ws_id, allow_external=allow_external).run(
        AgentRequest(
            workspace_id=ws_id,
            instruction=body.text,
            max_sensitivity=Sensitivity.RESTRICTED,
            top_k=body.top_k,
        )
    )
    answer = run.answer
    citations: list[Citation] = []
    if answer is not None:
        workspace = backend.workspace_for(ws_id, allow_external=allow_external)
        scope = context.workspace.kind
        citations = [
            Citation(
                claim_id=claim_id,
                source_span_id=span_id,
                artifact_id=artifact_id,
                scope=scope,
                sensitivity=sensitivity,
            )
            for claim_id, span_id, artifact_id, sensitivity in await workspace.citation_rows(
                answer.claims
            )
        ]
    restricted_evidence = any(
        c.sensitivity is not None and is_at_least(c.sensitivity, Sensitivity.RESTRICTED)
        for c in citations
    )
    routed_local = (not allow_external) or restricted_evidence
    return QueryResponse(
        run_id=str(run.run_id),
        status=run.status.value,
        answer=answer.text if answer is not None else run.summary,
        sufficient=answer.sufficient if answer is not None else False,
        routed_local=routed_local,
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


@router.get("/{workspace_id}/starter-questions", response_model=StarterQuestionsView)
async def starter_questions(context: MemberDep, backend: BackendDep) -> StarterQuestionsView:
    """A few grounded questions answerable from this workspace's recent evidence — the onboarding
    "first value" nudge (A5). Generated over recent claims/memory under the workspace's model policy
    (local model when external is disallowed); falls back to deterministic questions with no model.
    """
    policy = await backend.identity.get_model_policy(context.workspace.id)
    workspace = backend.workspace_for(
        context.workspace.id, allow_external=policy.allow_external_models
    )
    questions = await workspace.starter_questions(max_sensitivity=Sensitivity.RESTRICTED, count=3)
    return StarterQuestionsView(questions=questions)


@router.delete("/{workspace_id}/artifacts/{artifact_id}", response_model=ErasureView)
async def erase_artifact(
    artifact_id: str, context: WorkspaceAdminDep, backend: BackendDep
) -> ErasureView:
    """Right-to-erasure: tombstone the artifact's derived graph and delete its raw blob.

    Admin-gated (destructive) and resolved against the workspace's own engine, so one workspace can
    never erase another's artifact — an unknown id here is a 404, never a cross-workspace delete.
    """
    result = await backend.workspace_for(context.workspace.id).erase_artifact(artifact_id)
    if result is None:
        raise NotFoundError(f"no artifact {artifact_id!r} in this workspace")
    tombstoned = result.tombstoned
    return ErasureView(
        artifact_tombstoned=tombstoned.raw_artifacts > 0,
        normalized_docs=tombstoned.normalized_docs,
        parsed_docs=tombstoned.parsed_docs,
        segments=tombstoned.segments,
        claims=tombstoned.claims,
        mem_cells=tombstoned.mem_cells,
        blobs_erased=result.blobs_erased,
    )


# --- per-workspace model policy + spend ---------------------------------------------------------


def _policy_view(policy: WorkspaceModelPolicy) -> ModelPolicyView:
    return ModelPolicyView(
        workspace_id=str(policy.workspace_id),
        allow_external_models=policy.allow_external_models,
        daily_cost_cap_usd=policy.daily_cost_cap_usd,
    )


@router.get("/{workspace_id}/model-policy", response_model=ModelPolicyView)
async def get_model_policy(context: MemberDep, backend: BackendDep) -> ModelPolicyView:
    return _policy_view(await backend.identity.get_model_policy(context.workspace.id))


@router.put("/{workspace_id}/model-policy", response_model=ModelPolicyView)
async def set_model_policy(
    body: ModelPolicyUpdate, context: WorkspaceAdminDep, backend: BackendDep
) -> ModelPolicyView:
    policy = await backend.identity.set_model_policy(
        WorkspaceModelPolicy(
            workspace_id=context.workspace.id,
            allow_external_models=body.allow_external_models,
            daily_cost_cap_usd=body.daily_cost_cap_usd,
        )
    )
    return _policy_view(policy)


@router.get("/{workspace_id}/spend", response_model=SpendView)
async def get_spend(context: WorkspaceAdminDep, backend: BackendDep) -> SpendView:
    ws_id = context.workspace.id
    total = backend.spend.today_total(ws_id) if backend.spend is not None else 0.0
    by_task = backend.spend.today_by_task(ws_id) if backend.spend is not None else {}
    return SpendView(workspace_id=str(ws_id), today_total_usd=total, today_by_task=by_task)
