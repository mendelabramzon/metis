/*
 * Wire DTOs from the gateway that the frontend consumes (B3+). Field names match the gateway's
 * pydantic views verbatim (snake_case) — mapping to camelCase domain shapes happens at the edges.
 */

import type { ActionRisk, Sensitivity } from "@/domain/types";

export type WorkspaceKind = "personal" | "shared" | "external";

/** `POST /organizations` (operator) — the deployment's organization. */
export interface OrganizationView {
  id: string;
  name: string;
}

/** `GET /users/me` / `POST /users` — the user-id bearer resolves to this. */
export interface UserView {
  id: string;
  organization_id: string;
  email: string;
  display_name: string;
  active: boolean;
}

/** `GET /workspaces` items. No per-caller role field — derive owner-vs-member from `owner_id`. */
export interface WorkspaceView {
  id: string;
  organization_id: string;
  kind: WorkspaceKind;
  name: string;
  owner_id: string | null;
  default_sensitivity: Sensitivity;
}

// --- sources (deployment sources; scope-token gated) ----------------------------------------

/** `GET /sources` item. No health/state field yet — derive a default "connected". */
export interface SourceView {
  id: string;
  workspace_id: string;
  name: string;
  connector: string;
  sensitivity: Sensitivity;
  auth_method: string;
}

/** `DELETE /sources/{id}` — what the cascade erased (derived graphs tombstoned + blobs deleted). */
export interface SourceErasureView {
  artifacts: number;
  claims: number;
  mem_cells: number;
  blobs_erased: number;
}

/** `GET /sources/connectors` — the catalog the add-source form is built from. */
export interface ConnectorView {
  name: string;
  auth_method: string;
  default_sensitivity: Sensitivity;
  requires_config: boolean;
}

/** `POST /sources` body. `config` is connector-specific (empty for OAuth/no-auth connectors). */
export interface SourceCreate {
  name: string;
  connector: string;
  sensitivity: Sensitivity;
  config: Record<string, unknown>;
  workspace_id?: string;
}

/** `GET /telegram/chats` — a chat the bot has seen on a Business connection (E4). */
export interface TelegramChatView {
  business_connection_id: string;
  chat_id: number;
  chat_type: string;
  title: string;
  last_message_id: number;
}

/** `GET /oauth/{connector}/authorize` — the consent URL to send the user to. */
export interface AuthorizeView {
  authorize_url: string;
  state: string;
}

/** Per-file parse status from `POST /workspaces/{ws}/upload` (E2). */
export interface ParseStatus {
  filename: string;
  status: string;
  doc_id?: string;
  media_type?: string;
  segments?: number;
  claims?: number;
  coverage?: number | null;
  page_count?: number | null;
  tables?: number;
  warnings?: string[];
  parse_path?: string;
  error?: string;
}

export interface UploadResponse {
  files: ParseStatus[];
}

export type MembershipRole = "owner" | "admin" | "member" | "viewer" | "auditor";

export const MEMBERSHIP_ROLES: readonly MembershipRole[] = [
  "owner",
  "admin",
  "member",
  "viewer",
  "auditor",
];

/** `GET /workspaces/{ws}/members` item (workspace-admin gated). */
export interface MembershipView {
  id: string;
  workspace_id: string;
  user_id: string;
  role: MembershipRole;
}

/** `POST /workspaces/{ws}/invites` (A6, admin) → a single-use invite token. */
export interface InviteView {
  id: string;
  workspace_id: string;
  role: MembershipRole;
  token: string;
  redeemed: boolean;
}

/** `POST /invites/{token}/redeem` (A6). `user_id` is the new user's bearer token. */
export interface InviteRedeemView {
  user_id: string;
  organization_id: string;
  workspace_id: string;
}

/** `POST /workspaces/{ws}/query` body. */
export interface QueryRequestBody {
  text: string;
  top_k?: number;
}

/** A cited claim behind an answer (A1 added scope + sensitivity). */
export interface Citation {
  claim_id: string;
  source_span_id: string | null;
  artifact_id: string | null;
  /** Personal/shared/external origin of the cited source's workspace (A1). */
  scope: WorkspaceKind | null;
  sensitivity: Sensitivity | null;
}

/** One side of an answer-time disagreement (A3). */
export interface ConflictSideView {
  claim_id: string;
  text: string;
  source_span_id: string | null;
  artifact_id: string | null;
  sensitivity: Sensitivity | null;
}

/** Conflicting evidence surfaced at answer time (A3): same subject+predicate, differing claims. */
export interface DisagreementView {
  predicate: string;
  sides: ConflictSideView[];
}

export interface QueryResponse {
  run_id: string;
  status: string;
  answer: string;
  sufficient: boolean;
  /** True when the answer's cited evidence stayed on local/on-device models (A2); null on legacy path. */
  routed_local: boolean | null;
  citations: Citation[];
  contradictions: string[];
  disagreements: DisagreementView[];
  filebacks: number;
  pending_approvals: string[];
}

// --- evidence drill-down (a citation back through the truth hierarchy) ----------------------

/** One source span behind a claim: its location and the exact quoted source text. */
export interface SpanView {
  source_span_id: string;
  artifact_id: string;
  doc_id: string | null;
  char_start: number;
  char_end: number;
  page: number | null;
  quote: string | null;
}

/** `GET /workspaces/{ws}/claims/{id}` — a claim with its supporting spans expanded. */
export interface ClaimEvidenceView {
  claim_id: string;
  text: string;
  confidence: number;
  negated: boolean;
  sensitivity: Sensitivity;
  spans: SpanView[];
}

/** `GET /workspaces/{ws}/artifacts/{id}` — the source document a span points back to. */
export interface ArtifactEvidenceView {
  artifact_id: string;
  filename: string | null;
  media_type: string;
  byte_size: number;
  kind: string;
  connector: string;
  source_id: string | null;
  created_at: string;
  tombstoned: boolean;
}

// --- proposed actions (the command surface; operator/scope-token gated) ---------------------

export type ActionKind =
  | "answer"
  | "find_evidence"
  | "inspect_source"
  | "draft_response"
  | "create_memory"
  | "create_wiki_patch"
  | "start_sync"
  | "propose_source_change";

export type ActionStatus = "proposed" | "approved" | "rejected" | "executed" | "failed";

/** A proposed-action card: what the system understood, its risk, and the recorded decision. */
export interface ProposedActionView {
  id: string;
  workspace_id: string;
  kind: ActionKind;
  risk: ActionRisk;
  command: string;
  summary: string;
  parameters: Record<string, unknown>;
  sensitivity: Sensitivity;
  audit_target: string;
  status: ActionStatus;
  decided_by: string | null;
  decision_note: string;
}

/** The result of executing an action: the new status + what the run produced. */
export interface ActionExecutionView {
  action: ProposedActionView;
  detail: string;
  answer: string | null;
  sufficient: boolean | null;
  citations: Citation[];
  job_id: string | null;
  doc_id: string | null;
  patch_id: string | null;
  source_id: string | null;
}

// --- review queue (contradictions + approvals) ----------------------------------------------

export type ContradictionStatus = "open" | "resolved" | "dismissed";

/** `GET /workspaces/{ws}/contradictions` — conflicting evidence for review (member-gated). */
export interface ContradictionView {
  contradiction_id: string;
  summary: string;
  explanation: string;
  status: ContradictionStatus;
  claim_ids: string[];
  sensitivity: Sensitivity;
  created_at: string;
}

/** `GET /approvals` — one inbox over agent/skill actions and wiki patches (operator-gated). */
export interface InboxItemView {
  /** "action" | "wiki_patch" */
  kind: string;
  id: string;
  summary: string;
  status: string;
}

/** `GET/PUT /workspaces/{ws}/model-policy` — whether external models may see this workspace's data. */
export interface ModelPolicyView {
  workspace_id: string;
  allow_external_models: boolean;
  daily_cost_cap_usd: number | null;
}

/** `GET /workspaces/{ws}/spend` — today's model spend (admin-gated). */
export interface SpendView {
  workspace_id: string;
  today_total_usd: number;
  today_by_task: Record<string, number>;
}

// --- operations (operator-only) -------------------------------------------------------------

export interface HealthView {
  status: string;
  service: string;
}

/** `GET /providers` — a model enabled by its capability manifest (operator). */
export interface ProviderView {
  provider: string;
  model_id: string;
  kind: string;
  privacy_tier: string;
  context_window: number;
  supports_tools: boolean;
}

export type JobState =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "retrying";

/** `GET /jobs` — a background job (operator). */
export interface JobView {
  id: string;
  kind: string;
  state: JobState;
  attempts: number;
  error: string | null;
}

/** `GET /audit` — an audit/event row (operator-gated; global, no workspace field). */
export interface AuditView {
  id: string;
  action: string;
  actor: string;
  target_id: string | null;
  target_kind: string | null;
  sensitivity: string | null;
  occurred_at: string;
}

/** The gateway's error envelope (see install_error_handlers). */
export interface ApiErrorBody {
  error?: { message?: string; code?: string };
}
