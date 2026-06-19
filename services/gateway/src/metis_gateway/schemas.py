"""Request/response models for the HTTP boundary.

These are thin DTOs: the gateway speaks protocol objects internally and projects just what a client
needs onto stable JSON shapes (citations as flat ids, an inbox item that unifies actions and
patches, a job view that exposes retry state). Protocol enums are reused directly so the wire vocab
matches the engine's.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from metis_protocol import (
    JobState,
    ModelKind,
    ModelTier,
    PrivacyTier,
    Role,
    Sensitivity,
    SkillOutcome,
    WorkspaceKind,
)

# --- sources + ingestion -----------------------------------------------------------------------


class SourceCreate(BaseModel):
    name: str
    connector: str
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    workspace_id: str | None = None  # defaults to the deployment's configured workspace


class SourceView(BaseModel):
    id: str
    workspace_id: str
    name: str
    connector: str
    sensitivity: Sensitivity
    auth_method: str


class IngestRequest(BaseModel):
    filename: str
    content: str
    sensitivity: Sensitivity | None = None  # defaults to the source's sensitivity


class IngestResponse(BaseModel):
    doc_id: str
    artifacts: int
    claims: int


class ParseStatus(BaseModel):
    """The visible per-file result of an upload: parsed, an unsupported type, or a parse failure."""

    filename: str
    status: Literal["parsed", "unsupported", "failed"]
    doc_id: str | None = None
    media_type: str | None = None
    segments: int = 0
    claims: int = 0
    error: str | None = None


class UploadResponse(BaseModel):
    files: list[ParseStatus]


# --- model providers (operator) ----------------------------------------------------------------


class ProviderView(BaseModel):
    """An operator's view of a model enabled by its capability manifest."""

    provider: str
    model_id: str
    kind: ModelKind
    privacy_tier: PrivacyTier
    tiers: list[ModelTier]
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_json: bool
    embedding_dim: int | None = None


# --- query / chat ------------------------------------------------------------------------------


class QueryRequestBody(BaseModel):
    text: str
    top_k: int | None = None


class Citation(BaseModel):
    claim_id: str
    source_span_id: str | None = None
    artifact_id: str | None = None


class QueryResponse(BaseModel):
    run_id: str
    status: str
    answer: str
    sufficient: bool
    citations: list[Citation] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    filebacks: int = 0
    pending_approvals: list[str] = Field(default_factory=list)


# --- skills ------------------------------------------------------------------------------------


class SkillView(BaseModel):
    name: str
    version: str
    description: str
    category: str
    requires_approval: bool


class SkillRunRequest(BaseModel):
    name: str
    version: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class SkillRunResponse(BaseModel):
    outcome: SkillOutcome
    output: JsonValue = None
    error: str | None = None
    approval_required: bool = False
    artifacts: int = 0


# --- approvals (unified inbox: actions + wiki patches) -----------------------------------------


class InboxItemView(BaseModel):
    kind: str  # "action" | "wiki_patch"
    id: str
    summary: str
    status: str


class ApproveRequest(BaseModel):
    note: str = ""


# --- jobs / ops --------------------------------------------------------------------------------


class JobView(BaseModel):
    id: str
    kind: str
    state: JobState
    attempts: int
    error: str | None = None


# --- audit -------------------------------------------------------------------------------------


class AuditView(BaseModel):
    id: str
    action: str
    actor: str
    target_id: str | None = None
    target_kind: str | None = None
    sensitivity: str | None = None
    occurred_at: str


# --- wiki --------------------------------------------------------------------------------------


class WikiPageView(BaseModel):
    id: str
    title: str
    slug: str


class WikiPatchView(BaseModel):
    id: str
    summary: str
    status: str


# --- identity + workspaces ---------------------------------------------------------------------


class OrganizationCreate(BaseModel):
    name: str


class OrganizationView(BaseModel):
    id: str
    name: str


class UserCreate(BaseModel):
    organization_id: str
    email: str
    display_name: str


class UserView(BaseModel):
    id: str
    organization_id: str
    email: str
    display_name: str
    active: bool


class WorkspaceCreate(BaseModel):
    name: str
    kind: WorkspaceKind = WorkspaceKind.SHARED


class WorkspaceView(BaseModel):
    id: str
    organization_id: str
    kind: WorkspaceKind
    name: str
    owner_id: str | None = None
    default_sensitivity: Sensitivity


class MembershipCreate(BaseModel):
    user_id: str
    role: Role = Role.MEMBER


class MembershipView(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    role: Role


class ModelPolicyView(BaseModel):
    workspace_id: str
    allow_external_models: bool
    daily_cost_cap_usd: float | None = None


class ModelPolicyUpdate(BaseModel):
    allow_external_models: bool = True
    daily_cost_cap_usd: float | None = None


class SpendView(BaseModel):
    workspace_id: str
    today_total_usd: float
    today_by_task: dict[str, float] = Field(default_factory=dict)
