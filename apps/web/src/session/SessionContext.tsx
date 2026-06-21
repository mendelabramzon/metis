/* eslint-disable react-refresh/only-export-components --
   Idiomatic context + provider + hook colocation. The provider rarely changes in dev, so the
   Fast-Refresh constraint this rule guards doesn't apply here. */
import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { Principal, Role, Session } from "./types";

const SessionCtx = createContext<Session | null>(null);

// A stand-in principal so the shell, nav, and role-gating are demonstrable before B3 wires real
// auth. B3 replaces this provider with one backed by `GET /users/me` + the two gateway principals.
const MOCK_PRINCIPAL: Principal = {
  id: "u_demo",
  email: "you@example.com",
  role: "admin",
  isOperator: true,
};

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>(MOCK_PRINCIPAL.role);
  const value = useMemo<Session>(
    () => ({ principal: { ...MOCK_PRINCIPAL, role }, setRole }),
    [role],
  );
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error("useSession must be used within a SessionProvider");
  return ctx;
}
