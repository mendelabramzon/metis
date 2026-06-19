"""Request/response models for the HTTP boundary.

These are thin DTOs: the gateway speaks protocol objects internally and projects just what a client
needs onto stable JSON shapes (citations as flat ids, an inbox item that unifies actions and
patches, a job view that exposes retry state). Protocol enums are reused directly so the wire vocab
matches the engine's.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from metis_protocol import (
    ContradictionStatus,
    JobState,
    MemoryOp,
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


class SyncResponse(BaseModel):
    """The queued connector-sync job: the source ingests via this job, not an inline POST."""

    job_id: str
    source_id: str


class AuthorizeView(BaseModel):
    """The Google consent URL to open, plus the CSRF state the callback verifies."""

    authorize_url: str
    state: str


class ConnectionView(BaseModel):
    """The result of an OAuth callback: which connector was connected."""

    connector: str
    status: str


class IngestRequest(BaseModel):
    filename: str
    content: str
    sensitivity: Sensitivity | None = None  # defaults to the source's sensitivity


class IngestResponse(BaseModel):
    doc_id: str
    artifacts: int
    claims: int


class ErasureView(BaseModel):
    """The outcome of erasing one raw artifact: what the tombstone cascade marked, and whether the
    raw blob was physically deleted (durable backend only)."""

    artifact_tombstoned: bool
    normalized_docs: int
    parsed_docs: int
    segments: int
    claims: int
    mem_cells: int
    blobs_erased: int


class SourceErasureView(BaseModel):
    """The outcome of deleting a source: how many of its artifacts were erased (derived graphs
    tombstoned + blobs deleted). The source registration itself is removed too."""

    artifacts: int
    claims: int
    mem_cells: int
    blobs_erased: int


class UserErasureView(BaseModel):
    """The outcome of erasing a user: their personal-workspace artifacts erased and the account
    deactivated (locked out). Shared-workspace contributions and the audit trail are kept."""

    user_id: str
    deactivated: bool
    artifacts: int
    claims: int
    mem_cells: int
    blobs_erased: int


# --- evidence drill-down (the evidence browser) ------------------------------------------------


class SpanView(BaseModel):
    """One source span behind a claim: its location and the exact quoted source text."""

    source_span_id: str
    artifact_id: str
    doc_id: str | None = None
    char_start: int
    char_end: int
    page: int | None = None
    quote: str | None = None


class ClaimEvidenceView(BaseModel):
    """A claim with its supporting spans expanded — the evidence behind a citation."""

    claim_id: str
    text: str
    confidence: float
    negated: bool
    sensitivity: Sensitivity
    spans: list[SpanView]


class ArtifactEvidenceView(BaseModel):
    """A raw artifact's metadata — the source document a span points back to."""

    artifact_id: str
    filename: str | None = None
    media_type: str
    byte_size: int
    kind: str
    connector: str
    source_id: str | None = None
    created_at: datetime
    tombstoned: bool


class MemCellEvidenceView(BaseModel):
    """A consolidated memory cell and the claim ids it rests on."""

    mem_cell_id: str
    summary: str
    sensitivity: Sensitivity
    claim_ids: list[str]


# --- contradiction inbox -----------------------------------------------------------------------


class ContradictionView(BaseModel):
    """A detected conflict between claims, surfaced for review — never silently merged."""

    contradiction_id: str
    summary: str
    explanation: str
    status: ContradictionStatus
    claim_ids: list[str]
    sensitivity: Sensitivity
    created_at: datetime


class ContradictionUpdate(BaseModel):
    """Resolve or dismiss a contradiction — the only review transitions (no reopen via the API)."""

    status: Literal[ContradictionStatus.RESOLVED, ContradictionStatus.DISMISSED]


# --- memory review (the write/manage/read loop) ------------------------------------------------


class MemoryCellView(BaseModel):
    """A consolidated memory cell in the review queue (claims drill in via the evidence API)."""

    mem_cell_id: str
    summary: str
    sensitivity: Sensitivity
    claim_ids: list[str]
    created_at: datetime


class MemoryRevisionRequest(BaseModel):
    """An optional reason recorded on a retract/supersede review action."""

    reason: str = ""


class MemoryRevisionResult(BaseModel):
    """Confirmation of a memory-review action: the cell and the revision applied."""

    mem_cell_id: str
    op: MemoryOp
    summary: str


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
