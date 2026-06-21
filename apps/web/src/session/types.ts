/*
 * Session vocabulary (B2). The role model mirrors the server-deployment roadmap's workspace roles
 * (owner, admin, member, viewer, auditor). B2 establishes the shape + a role-gated nav; B3 replaces
 * the mock provider with real auth over the two gateway principals (the user-id bearer for
 * per-workspace surfaces; the operator token for Operations).
 */

export type Role = "owner" | "admin" | "member" | "viewer" | "auditor";

export const ROLES: readonly Role[] = ["owner", "admin", "member", "viewer", "auditor"];

export interface Principal {
  /** The user-id bearer used for membership-gated, per-workspace surfaces. */
  id: string;
  email: string;
  /** The signed-in user's role in the active workspace — drives role-based nav hiding. */
  role: Role;
  /** Whether this user also holds the operator principal (gates Operations; G5). */
  isOperator: boolean;
}

export interface Session {
  principal: Principal | null;
  /** B2 demo affordance: switch the active role to show nav hiding. B3 removes this. */
  setRole: (role: Role) => void;
}
