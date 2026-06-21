/*
 * Session vocabulary (B3). Backed by real auth over the two gateway principals: the user-id bearer
 * (identity + per-workspace surfaces) and the operator/scope token (operator surfaces / Operations).
 *
 * Role note: the gateway's `/workspaces` list carries no per-caller role, so the active role is
 * derived — owner when you own the active workspace, member otherwise. Finer roles (admin/viewer/
 * auditor) need a small backend addition (the caller's role on the workspace), a clean follow-up
 * that G2 will want anyway.
 */

import type { Sensitivity } from "@/domain/types";
import type { WorkspaceKind } from "@/api/types";

export type Role = "owner" | "admin" | "member" | "viewer" | "auditor";

export interface SessionUser {
  id: string;
  email: string;
  displayName: string;
  organizationId: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  kind: WorkspaceKind;
  ownerId: string | null;
  defaultSensitivity: Sensitivity;
}

export type SessionStatus = "loading" | "anonymous" | "authenticated";

export interface SignInInput {
  /** The user-id bearer (a dev stand-in for a real session; sessions/SSO are a backend follow-up). */
  userId: string;
  /** Optional operator/scope token to also hold the operator principal. */
  operatorToken?: string;
}

export interface Session {
  status: SessionStatus;
  user: SessionUser | null;
  workspaces: WorkspaceSummary[];
  activeWorkspaceId: string | null;
  activeWorkspace: WorkspaceSummary | null;
  /** Derived role for the active workspace — drives role-based nav hiding. */
  role: Role;
  /** Whether a valid operator token is held (gates Operations; G5). */
  isOperator: boolean;
  /** The user-id bearer for data fetching, or null when anonymous. */
  userBearer: string | null;
  operatorToken: string | null;

  signIn: (input: SignInInput) => Promise<void>;
  signOut: () => void;
  setActiveWorkspace: (id: string) => void;
  refreshWorkspaces: () => Promise<void>;
}
