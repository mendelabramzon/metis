/*
 * Wire DTOs from the gateway that the frontend consumes (B3+). Field names match the gateway's
 * pydantic views verbatim (snake_case) — mapping to camelCase domain shapes happens at the edges.
 */

import type { ActionRisk, Sensitivity } from "@/domain/types";

export type WorkspaceKind = "personal" | "shared" | "external";

/** `GET /users/me` — the user-id bearer resolves to this. */
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

/** `GET /sources/connectors` — the catalog the add-source form is built from. */
export interface ConnectorView {
  name: string;
  auth_method: string;
  default_sensitivity: Sensitivity;
  requires_config: boolean;
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

/** The gateway's error envelope (see install_error_handlers). */
export interface ApiErrorBody {
  error?: { message?: string; code?: string };
}
