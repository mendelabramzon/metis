/* Session persistence (B3): the user-id bearer, the optional operator token, and the last active
   workspace, in localStorage. All access is guarded — private-mode / denied storage degrades to a
   non-persisted session rather than throwing. */

const KEYS = {
  userId: "metis.userId",
  operatorToken: "metis.operatorToken",
  activeWorkspaceId: "metis.activeWorkspaceId",
  scope: "metis.scope",
} as const;

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — session simply won't persist */
  }
}

export interface PersistedSession {
  userId: string | null;
  operatorToken: string | null;
  activeWorkspaceId: string | null;
  scope: string | null;
}

export function loadPersisted(): PersistedSession {
  return {
    userId: read(KEYS.userId),
    operatorToken: read(KEYS.operatorToken),
    activeWorkspaceId: read(KEYS.activeWorkspaceId),
    scope: read(KEYS.scope),
  };
}

export function persistUserId(value: string | null): void {
  write(KEYS.userId, value);
}

export function persistOperatorToken(value: string | null): void {
  write(KEYS.operatorToken, value);
}

export function persistActiveWorkspaceId(value: string | null): void {
  write(KEYS.activeWorkspaceId, value);
}

export function persistScope(value: string | null): void {
  write(KEYS.scope, value);
}

export function clearPersisted(): void {
  persistUserId(null);
  persistOperatorToken(null);
  persistActiveWorkspaceId(null);
  persistScope(null);
}
