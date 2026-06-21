/* eslint-disable react-refresh/only-export-components --
   Idiomatic context + provider + hook colocation. The provider rarely changes in dev, so the
   Fast-Refresh constraint this rule guards doesn't apply here. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { getMe, listWorkspaces, probeOperator } from "@/api/client";
import type { UserView, WorkspaceView } from "@/api/types";

import {
  clearPersisted,
  loadPersisted,
  persistActiveWorkspaceId,
  persistOperatorToken,
  persistUserId,
} from "./storage";
import type { Role, Session, SessionUser, SignInInput, WorkspaceSummary } from "./types";

const SessionCtx = createContext<Session | null>(null);

const toUser = (v: UserView): SessionUser => ({
  id: v.id,
  email: v.email,
  displayName: v.display_name,
  organizationId: v.organization_id,
});

const toSummary = (v: WorkspaceView): WorkspaceSummary => ({
  id: v.id,
  name: v.name,
  kind: v.kind,
  ownerId: v.owner_id,
  defaultSensitivity: v.default_sensitivity,
});

/** Prefer the last-active workspace, else the user's personal workspace, else the first. */
function pickActiveId(
  workspaces: WorkspaceSummary[],
  preferredId: string | null,
  userId: string,
): string | null {
  if (preferredId && workspaces.some((w) => w.id === preferredId)) return preferredId;
  const personal = workspaces.find((w) => w.kind === "personal" && w.ownerId === userId);
  return personal?.id ?? workspaces[0]?.id ?? null;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Session["status"]>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(null);
  const [userBearer, setUserBearer] = useState<string | null>(null);
  const [operatorToken, setOperatorToken] = useState<string | null>(null);

  // Restore a persisted session on load: validate the user bearer, then (best-effort) the operator
  // token. An invalid user bearer → anonymous; a stale operator token is simply dropped.
  useEffect(() => {
    const persisted = loadPersisted();
    if (!persisted.userId) {
      setStatus("anonymous");
      return;
    }
    const controller = new AbortController();
    const bearer = persisted.userId;
    void (async () => {
      try {
        const me = toUser(await getMe(bearer, controller.signal));
        const ws = (await listWorkspaces(bearer, controller.signal)).map(toSummary);
        let opToken: string | null = null;
        if (persisted.operatorToken) {
          try {
            await probeOperator(persisted.operatorToken, controller.signal);
            opToken = persisted.operatorToken;
          } catch {
            if (controller.signal.aborted) return;
            persistOperatorToken(null);
          }
        }
        setUser(me);
        setWorkspaces(ws);
        setUserBearer(bearer);
        setOperatorToken(opToken);
        setActiveWorkspaceIdState(pickActiveId(ws, persisted.activeWorkspaceId, me.id));
        setStatus("authenticated");
      } catch {
        if (controller.signal.aborted) return;
        clearPersisted();
        setStatus("anonymous");
      }
    })();
    return () => controller.abort();
  }, []);

  const signIn = useCallback(async ({ userId, operatorToken: opInput }: SignInInput) => {
    // Gather everything before mutating state, so a failure leaves the session untouched.
    const me = toUser(await getMe(userId));
    const ws = (await listWorkspaces(userId)).map(toSummary);
    let opToken: string | null = null;
    if (opInput) {
      await probeOperator(opInput);
      opToken = opInput;
    }
    const activeId = pickActiveId(ws, loadPersisted().activeWorkspaceId, me.id);
    setUser(me);
    setWorkspaces(ws);
    setUserBearer(userId);
    setOperatorToken(opToken);
    setActiveWorkspaceIdState(activeId);
    setStatus("authenticated");
    persistUserId(userId);
    persistOperatorToken(opToken);
    persistActiveWorkspaceId(activeId);
  }, []);

  const signOut = useCallback(() => {
    clearPersisted();
    setUser(null);
    setWorkspaces([]);
    setUserBearer(null);
    setOperatorToken(null);
    setActiveWorkspaceIdState(null);
    setStatus("anonymous");
  }, []);

  const setActiveWorkspace = useCallback((id: string) => {
    setActiveWorkspaceIdState(id);
    persistActiveWorkspaceId(id);
  }, []);

  const refreshWorkspaces = useCallback(async () => {
    if (!userBearer) return;
    setWorkspaces((await listWorkspaces(userBearer)).map(toSummary));
  }, [userBearer]);

  const value = useMemo<Session>(() => {
    const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? null;
    const role: Role =
      activeWorkspace && user && activeWorkspace.ownerId === user.id ? "owner" : "member";
    return {
      status,
      user,
      workspaces,
      activeWorkspaceId,
      activeWorkspace,
      role,
      isOperator: operatorToken !== null,
      userBearer,
      operatorToken,
      signIn,
      signOut,
      setActiveWorkspace,
      refreshWorkspaces,
    };
  }, [
    status,
    user,
    workspaces,
    activeWorkspaceId,
    operatorToken,
    userBearer,
    signIn,
    signOut,
    setActiveWorkspace,
    refreshWorkspaces,
  ]);

  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error("useSession must be used within a SessionProvider");
  return ctx;
}
