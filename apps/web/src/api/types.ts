/*
 * Wire DTOs from the gateway that the frontend consumes (B3+). Field names match the gateway's
 * pydantic views verbatim (snake_case) — mapping to camelCase domain shapes happens at the edges.
 */

import type { Sensitivity } from "@/domain/types";

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

/** The gateway's error envelope (see install_error_handlers). */
export interface ApiErrorBody {
  error?: { message?: string; code?: string };
}
