import type { Citation } from "@/api/types";
import type { WorkspaceScope } from "@/domain/types";

/** Map a citation's workspace-kind origin to the personal/shared scope badges (external → shared). */
export const scopeForCitation = (scope: Citation["scope"]): WorkspaceScope | null =>
  scope === "personal" ? "personal" : scope === null ? null : "shared";
