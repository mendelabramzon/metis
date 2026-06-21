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
  ClaimEvidenceView,
  InviteRedeemView,
  ProposedActionView,
  QueryRequestBody,
  QueryResponse,
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
