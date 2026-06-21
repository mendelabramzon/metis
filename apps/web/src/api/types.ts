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

/** The gateway's error envelope (see install_error_handlers). */
export interface ApiErrorBody {
  error?: { message?: string; code?: string };
}
