/*
 * The low-level gateway client (B3). One typed `request` over fetch + small endpoint helpers the
 * session layer uses. Two auth modes are expressed by which bearer the caller passes: the user-id
 * bearer for identity/per-workspace endpoints, the operator/scope token for operator surfaces.
 *
 * Paths are root-relative (no `/api` prefix); the Vite dev proxy forwards them to the gateway, and
 * in production the gateway serves the SPA from the same origin.
 */

import type {
  ActionExecutionView,
  ApiErrorBody,
  ArtifactEvidenceView,
  AuditView,
  AuthorizeView,
  ClaimEvidenceView,
  ConnectorView,
  ContradictionStatus,
  ContradictionView,
  InboxItemView,
  InviteRedeemView,
  InviteView,
  MembershipRole,
  MembershipView,
  ModelPolicyView,
  SpendView,
  ProposedActionView,
  QueryRequestBody,
  QueryResponse,
  SourceCreate,
  SourceErasureView,
  SourceView,
  TelegramChatView,
  UploadResponse,
  UserView,
  WorkspaceView,
} from "./types";

/** A non-2xx response, carrying the gateway's status + decoded error message/code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Authorization bearer: the user-id, or the operator token. */
  bearer?: string;
  signal?: AbortSignal;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.bearer) headers["Authorization"] = `Bearer ${options.bearer}`;
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let res: Response;
  try {
    res = await fetch(path, {
      method: options.method ?? "GET",
      headers,
      ...(body !== undefined ? { body } : {}),
      ...(options.signal ? { signal: options.signal } : {}),
    });
  } catch (cause) {
    // Network/connection failure — distinct from an HTTP error response.
    throw new ApiError(0, "Couldn’t reach the server. Check your connection and try again.");
  }

  const raw = await res.text();
  let data: unknown = null;
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const envelope = data as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      envelope?.error?.message ?? res.statusText ?? "Request failed",
      envelope?.error?.code,
    );
  }
  return data as T;
}

// --- endpoint helpers -----------------------------------------------------------------------

/** Validate the user-id bearer and return the user (401 if unknown/inactive). */
export const getMe = (bearer: string, signal?: AbortSignal): Promise<UserView> =>
  request<UserView>("/users/me", { bearer, ...(signal ? { signal } : {}) });

/** The workspaces the signed-in user belongs to. */
export const listWorkspaces = (bearer: string, signal?: AbortSignal): Promise<WorkspaceView[]> =>
  request<WorkspaceView[]>("/workspaces", { bearer, ...(signal ? { signal } : {}) });

/** Validate the operator token via a read-only operator endpoint; resolves if valid, throws if not. */
export const probeOperator = async (token: string, signal?: AbortSignal): Promise<void> => {
  await request<unknown>("/providers", { bearer: token, ...(signal ? { signal } : {}) });
};

/** Ask the active workspace for a grounded answer (membership-gated). A policy block is a 403. */
export const queryWorkspace = (
  bearer: string,
  workspaceId: string,
  body: QueryRequestBody,
  signal?: AbortSignal,
): Promise<QueryResponse> =>
  request<QueryResponse>(`/workspaces/${encodeURIComponent(workspaceId)}/query`, {
    method: "POST",
    body,
    bearer,
    ...(signal ? { signal } : {}),
  });

/** A citation's claim + the source spans (with quotes) behind it. */
export const getClaimEvidence = (
  bearer: string,
  workspaceId: string,
  claimId: string,
  signal?: AbortSignal,
): Promise<ClaimEvidenceView> =>
  request<ClaimEvidenceView>(
    `/workspaces/${encodeURIComponent(workspaceId)}/claims/${encodeURIComponent(claimId)}`,
    { bearer, ...(signal ? { signal } : {}) },
  );

/** The source artifact (filename, type, ingest date) a span points back to. */
export const getArtifactEvidence = (
  bearer: string,
  workspaceId: string,
  artifactId: string,
  signal?: AbortSignal,
): Promise<ArtifactEvidenceView> =>
  request<ArtifactEvidenceView>(
    `/workspaces/${encodeURIComponent(workspaceId)}/artifacts/${encodeURIComponent(artifactId)}`,
    { bearer, ...(signal ? { signal } : {}) },
  );

/** Upload files into a workspace (multipart; user-id bearer / membership). Per-file parse status. */
export async function uploadFiles(
  bearer: string,
  workspaceId: string,
  files: File[],
): Promise<UploadResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  let res: Response;
  try {
    // Send only the bearer — the browser sets the multipart Content-Type with its own boundary.
    res = await fetch(`/workspaces/${encodeURIComponent(workspaceId)}/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearer}` },
      body: form,
    });
  } catch {
    throw new ApiError(0, "Couldn’t reach the server. Check your connection and try again.");
  }
  const raw = await res.text();
  let data: unknown = null;
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const envelope = data as ApiErrorBody | null;
    throw new ApiError(res.status, envelope?.error?.message ?? res.statusText, envelope?.error?.code);
  }
  return data as UploadResponse;
}

/** The audit/event log (operator-gated; global). The Activity view filters it client-side. */
export const listAudit = (
  operatorToken: string,
  limit = 100,
  signal?: AbortSignal,
): Promise<AuditView[]> =>
  request<AuditView[]>(`/audit?limit=${limit}`, {
    bearer: operatorToken,
    ...(signal ? { signal } : {}),
  });

// --- model policy + spend (workspace member/admin; user bearer) -----------------------------

export const getModelPolicy = (
  bearer: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<ModelPolicyView> =>
  request<ModelPolicyView>(`/workspaces/${encodeURIComponent(workspaceId)}/model-policy`, {
    bearer,
    ...(signal ? { signal } : {}),
  });

export const setModelPolicy = (
  bearer: string,
  workspaceId: string,
  body: { allow_external_models: boolean; daily_cost_cap_usd: number | null },
): Promise<ModelPolicyView> =>
  request<ModelPolicyView>(`/workspaces/${encodeURIComponent(workspaceId)}/model-policy`, {
    method: "PUT",
    body,
    bearer,
  });

export const getSpend = (
  bearer: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<SpendView> =>
  request<SpendView>(`/workspaces/${encodeURIComponent(workspaceId)}/spend`, {
    bearer,
    ...(signal ? { signal } : {}),
  });

// --- members + invites (workspace-admin; user bearer) ---------------------------------------

export const listMembers = (
  bearer: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<MembershipView[]> =>
  request<MembershipView[]>(`/workspaces/${encodeURIComponent(workspaceId)}/members`, {
    bearer,
    ...(signal ? { signal } : {}),
  });

export const addMember = (
  bearer: string,
  workspaceId: string,
  userId: string,
  role: MembershipRole,
): Promise<MembershipView> =>
  request<MembershipView>(`/workspaces/${encodeURIComponent(workspaceId)}/members`, {
    method: "POST",
    body: { user_id: userId, role },
    bearer,
  });

/** Mint a single-use invite to this workspace (A6). The token forms the redeem link. */
export const createWorkspaceInvite = (
  bearer: string,
  workspaceId: string,
  role: MembershipRole,
): Promise<InviteView> =>
  request<InviteView>(`/workspaces/${encodeURIComponent(workspaceId)}/invites`, {
    method: "POST",
    body: { role },
    bearer,
  });

// --- review queue: contradictions (user bearer) + approvals (operator token) ----------------

export const listContradictions = (
  bearer: string,
  workspaceId: string,
  status: ContradictionStatus,
  signal?: AbortSignal,
): Promise<ContradictionView[]> =>
  request<ContradictionView[]>(
    `/workspaces/${encodeURIComponent(workspaceId)}/contradictions?status=${status}`,
    { bearer, ...(signal ? { signal } : {}) },
  );

/** Resolve or dismiss a contradiction (workspace writer). */
export const reviewContradiction = (
  bearer: string,
  workspaceId: string,
  contradictionId: string,
  status: ContradictionStatus,
): Promise<ContradictionView> =>
  request<ContradictionView>(
    `/workspaces/${encodeURIComponent(workspaceId)}/contradictions/${encodeURIComponent(contradictionId)}`,
    { method: "PATCH", body: { status }, bearer },
  );

/** The approval inbox: pending agent/skill actions + wiki patches (operator-gated). */
export const listApprovals = (
  operatorToken: string,
  signal?: AbortSignal,
): Promise<InboxItemView[]> =>
  request<InboxItemView[]>("/approvals", {
    bearer: operatorToken,
    ...(signal ? { signal } : {}),
  });

export const approveInboxItem = (
  operatorToken: string,
  kind: string,
  itemId: string,
  note = "",
): Promise<InboxItemView> =>
  request<InboxItemView>(
    `/approvals/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}/approve`,
    { method: "POST", body: { note }, bearer: operatorToken },
  );

// --- sources (deployment sources; pass the operator/scope token) ----------------------------

/** All configured sources for the deployment. */
export const listSources = (operatorToken: string, signal?: AbortSignal): Promise<SourceView[]> =>
  request<SourceView[]>("/sources", { bearer: operatorToken, ...(signal ? { signal } : {}) });

/** The connector catalog the add-source form is built from. */
export const listConnectors = (
  operatorToken: string,
  signal?: AbortSignal,
): Promise<ConnectorView[]> =>
  request<ConnectorView[]>("/sources/connectors", {
    bearer: operatorToken,
    ...(signal ? { signal } : {}),
  });

/** Register a source (operator-gated). */
export const createSource = (
  operatorToken: string,
  body: SourceCreate,
): Promise<SourceView> =>
  request<SourceView>("/sources", { method: "POST", body, bearer: operatorToken });

/** Chats the Telegram bot has seen on its Business connections (the selection list for E4). */
export const listTelegramChats = (
  operatorToken: string,
  signal?: AbortSignal,
): Promise<TelegramChatView[]> =>
  request<TelegramChatView[]>("/telegram/chats", {
    bearer: operatorToken,
    ...(signal ? { signal } : {}),
  });

/** Start a Google OAuth consent flow for a connector; returns the consent URL (or 409 if off). */
export const getOAuthAuthorizeUrl = (
  operatorToken: string,
  connector: string,
): Promise<AuthorizeView> =>
  request<AuthorizeView>(`/oauth/${encodeURIComponent(connector)}/authorize`, {
    bearer: operatorToken,
  });

/** Permanently delete a source: erase its artifacts (tombstone + blob) and remove it (operator). */
export const deleteSource = (
  operatorToken: string,
  sourceId: string,
): Promise<SourceErasureView> =>
  request<SourceErasureView>(`/sources/${encodeURIComponent(sourceId)}`, {
    method: "DELETE",
    bearer: operatorToken,
  });

/** Enqueue a connector-sync job for a source (operator-gated). */
export const syncSource = (
  operatorToken: string,
  sourceId: string,
): Promise<{ job_id: string; source_id: string }> =>
  request<{ job_id: string; source_id: string }>(
    `/sources/${encodeURIComponent(sourceId)}/sync`,
    { method: "POST", bearer: operatorToken },
  );

// --- proposed actions (the command surface; pass the operator/scope token) ------------------

/** Interpret a free-text command into a typed proposed action (shown before any execution). */
export const proposeAction = (
  operatorToken: string,
  command: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<ProposedActionView> =>
  request<ProposedActionView>("/actions", {
    method: "POST",
    body: { command, workspace_id: workspaceId },
    bearer: operatorToken,
    ...(signal ? { signal } : {}),
  });

/** Approve a proposed action (recording the actor); executing it is a separate gated step. */
export const approveAction = (
  operatorToken: string,
  actionId: string,
  note = "",
): Promise<ProposedActionView> =>
  request<ProposedActionView>(`/actions/${encodeURIComponent(actionId)}/approve`, {
    method: "POST",
    body: { note },
    bearer: operatorToken,
  });

export const rejectAction = (
  operatorToken: string,
  actionId: string,
  note = "",
): Promise<ProposedActionView> =>
  request<ProposedActionView>(`/actions/${encodeURIComponent(actionId)}/reject`, {
    method: "POST",
    body: { note },
    bearer: operatorToken,
  });

/** Run an action against the engines (risk-gated server-side: effectful needs prior approval). */
export const executeAction = (
  operatorToken: string,
  actionId: string,
): Promise<ActionExecutionView> =>
  request<ActionExecutionView>(`/actions/${encodeURIComponent(actionId)}/execute`, {
    method: "POST",
    bearer: operatorToken,
  });

/** Redeem an invite (unauthenticated). The returned `user_id` is the new user's bearer (A6). */
export const redeemInvite = (
  token: string,
  body: { email: string; display_name: string },
  signal?: AbortSignal,
): Promise<InviteRedeemView> =>
  request<InviteRedeemView>(`/invites/${encodeURIComponent(token)}/redeem`, {
    method: "POST",
    body,
    ...(signal ? { signal } : {}),
  });
