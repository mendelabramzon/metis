import type { ReactNode } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { BlockedState, Button, EmptyState } from "@/components";
import { useSession } from "@/session/SessionContext";

import { NAV, navForRole } from "./nav";

/** Land on the first section the current role can reach (Ask for most; Review for an auditor). */
export function IndexRedirect() {
  const { principal } = useSession();
  const first = principal ? navForRole(principal.role)[0] : undefined;
  if (!first) {
    return (
      <EmptyState
        title="No sections available"
        description="This role has no accessible sections. An admin can adjust the role or workspace membership."
      />
    );
  }
  return <Navigate to={first.path} replace />;
}

/**
 * Enforce a section's role allowlist for direct navigation (the nav already hides it). Renders a
 * calm, non-error "not available for your role" panel rather than leaking the section — keeping the
 * hide cosmetic *and* the access real.
 */
export function RequireRole({ navId, children }: { navId: string; children: ReactNode }) {
  const { principal } = useSession();
  const navigate = useNavigate();
  const item = NAV.find((n) => n.id === navId);
  const allowed = principal != null && item != null && item.allowedRoles.includes(principal.role);

  if (!allowed) {
    return (
      <BlockedState
        title="Not available for your role"
        description={
          item
            ? `${item.label} isn't accessible with the “${principal?.role}” role.`
            : "This section isn't accessible with your current role."
        }
        actions={
          <Button variant="secondary" onClick={() => navigate("/")}>
            Go to your start page
          </Button>
        }
      />
    );
  }
  return <>{children}</>;
}

export function NotFound() {
  const navigate = useNavigate();
  return (
    <EmptyState
      title="Page not found"
      description="That route doesn’t exist."
      actions={
        <Button variant="secondary" onClick={() => navigate("/")}>
          Go home
        </Button>
      }
    />
  );
}
