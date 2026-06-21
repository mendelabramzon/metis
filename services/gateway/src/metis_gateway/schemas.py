"""Request/response models for the HTTP boundary.

These are thin DTOs: the gateway speaks protocol objects internally and projects just what a client
needs onto stable JSON shapes (citations as flat ids, an inbox item that unifies actions and
patches, a job view that exposes retry state). Protocol enums are reused directly so the wire vocab
matches the engine's.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, JsonValue

from metis_protocol import (
    ActionKind,
    ActionRisk,
    ActionStatus,
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

if TYPE_CHECKING:  # runtime conflict value objects the disagreement views are built from
    from metis_runtime.query import Conflict, ConflictSide

# --- sources + ingestion -----------------------------------------------------------------------


class SourceCreate(BaseModel):
    name: str
    connector: str
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    workspace_id: str | None = None  # defaults to the deployment's configured workspace
    config: dict[str, JsonValue] = Field(default_factory=dict)  # connector-specific selection


class TelegramChatView(BaseModel):
    business_connection_id: str
    chat_id: int
    chat_type: str
    title: str
    last_message_id: int


class TelegramConnectStart(BaseModel):
    """Begin a TDLib login: QR by default, or supply a phone number for the code flow."""

    use_qr: bool = True
    phone: str | None = None


class TelegramConnectCode(BaseModel):
    code: str


class TelegramConnectPassword(BaseModel):
    password: str


class TelegramConnectView(BaseModel):
    """Where the login is + what to do next (a ``qr_link`` to scan while in ``wait_qr``)."""

    state: str
    qr_link: str | None = None


class SourceView(BaseModel):
    id: str
    workspace_id: str
    name: str
    connector: str
    sensitivity: Sensitivity
    auth_method: str


class ConnectorView(BaseModel):
    """A connector a source can be configured for — the source-setup form's catalog.

    ``auth_method`` tells the UI how the connector is authorized (so an ``oauth2`` one prompts the
    Google connect flow first); ``requires_config`` flags that it validates a connector-specific
    config payload (e.g. a Telegram chat selection)."""

    name: str
    auth_method: str
    default_sensitivity: Sensitivity
    requires_config: bool


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
    """The visible per-file result of an upload: parsed, an unsupported type, or a parse failure,
    plus the parse-quality report (coverage, page/table counts, warnings, the parse path taken)."""

    filename: str
    status: Literal["parsed", "unsupported", "failed"]
    doc_id: str | None = None
    media_type: str | None = None
    segments: int = 0
    claims: int = 0
    error: str | None = None
    coverage: float | None = None
    page_count: int | None = None
    tables: int = 0
    warnings: list[str] = Field(default_factory=list)
    parse_path: str | None = None


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


class ResearchRequest(BaseModel):
    """Enqueue a background research job: answer ``query`` and file a grounded proposal back."""

    query: str


class RuntimeJobView(BaseModel):
    """The queued runtime job; its result surfaces in the wiki review inbox once processed."""

    job_id: str
    kind: str


class Citation(BaseModel):
    claim_id: str
    source_span_id: str | None = None
    artifact_id: str | None = None
    scope: WorkspaceKind | None = None  # personal/shared origin of the cited source's workspace
    sensitivity: Sensitivity | None = None  # the cited claim's sensitivity tier


class ConflictSideView(BaseModel):
    """One position in an answer-time disagreement, with the source span behind it."""

    claim_id: str
    text: str
    source_span_id: str | None = None
    artifact_id: str | None = None
    sensitivity: Sensitivity | None = None

    @classmethod
    def from_side(cls, side: ConflictSide) -> ConflictSideView:
        return cls(
            claim_id=side.claim_id,
            text=side.text,
            source_span_id=side.source_span_id,
            artifact_id=side.artifact_id,
            sensitivity=side.sensitivity,
        )


class DisagreementView(BaseModel):
    """Conflicting evidence surfaced at answer time: same subject+predicate, differing claims."""

    predicate: str
    sides: list[ConflictSideView]

    @classmethod
    def from_conflict(cls, conflict: Conflict) -> DisagreementView:
        return cls(
            predicate=conflict.predicate,
            sides=[ConflictSideView.from_side(s) for s in conflict.sides],
        )


class QueryResponse(BaseModel):
    run_id: str
    status: str
    answer: str
    sufficient: bool
    # True when the answer's cited evidence stayed on local/on-device models — external disallowed,
    # or the evidence is RESTRICTED (which the router keeps local). None on the legacy /query path.
    routed_local: bool | None = None
    citations: list[Citation] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    disagreements: list[DisagreementView] = Field(default_factory=list)
    filebacks: int = 0
    pending_approvals: list[str] = Field(default_factory=list)


class StarterQuestionsView(BaseModel):
    """Grounded starter questions for a freshly-populated workspace (the onboarding nudge, A5)."""

    questions: list[str] = Field(default_factory=list)


class DigestView(BaseModel):
    """A 'while you were away' summary for a workspace since a timestamp (A7, on-demand).

    Scoped to the per-workspace, member-gated surfaces: new contradictions to review and facts
    added to memory since ``since``. The scheduled weekly digest + operator-scoped items (synced
    jobs, wiki proposals) are follow-ups.
    """

    since: str | None = None
    new_contradictions: int = 0
    contradictions: list[str] = Field(default_factory=list)  # summaries of the new ones
    new_facts: int = 0
    facts: list[str] = Field(default_factory=list)  # summaries of memory cells added
    highlights: list[str] = Field(default_factory=list)  # human-readable one-liners


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


class InviteCreate(BaseModel):
    role: Role = Role.MEMBER


class InviteView(BaseModel):
    id: str
    workspace_id: str
    role: Role
    token: str
    redeemed: bool


class InviteRedeem(BaseModel):
    email: str
    display_name: str


class InviteRedeemView(BaseModel):
    """The result of redeeming an invite: the provisioned user (whose id is the bearer token) and
    the shared workspace they joined."""

    user_id: str
    organization_id: str
    workspace_id: str


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


# --- proposed actions (the command surface) ----------------------------------------------------


class CommandRequest(BaseModel):
    command: str
    workspace_id: str | None = None  # defaults to the deployment's configured workspace


class DecisionRequest(BaseModel):
    note: str = ""


class ProposedActionView(BaseModel):
    """A proposed-action card: what the system understood, its risk, and the recorded decision."""

    id: str
    workspace_id: str
    kind: ActionKind
    risk: ActionRisk
    command: str
    summary: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    sensitivity: Sensitivity
    audit_target: str
    status: ActionStatus
    decided_by: str | None = None
    decision_note: str = ""


class ActionExecutionView(BaseModel):
    """The result of executing an action: the action at its new status plus what the run produced
    (a grounded answer + citations for the read-only kinds, a queued job id for START_SYNC)."""

    action: ProposedActionView
    detail: str
    answer: str | None = None
    sufficient: bool | None = None
    citations: list[Citation] = Field(default_factory=list)
    job_id: str | None = None
    doc_id: str | None = None
    patch_id: str | None = None
    source_id: str | None = None
