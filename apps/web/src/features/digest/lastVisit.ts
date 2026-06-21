/*
 * Per-user, per-workspace "last visit" timestamp for the return-loop digest (F4).
 *
 * The SPA owns this marker (the gateway's on-demand digest is stateless and just takes a `?since=`):
 * on entry we read the previous visit to ask "what changed since then", then advance it to now so a
 * given change is summarised once. Stored in localStorage and guarded — storage being unavailable
 * just means no "while you were away" line, never a crash.
 */

const key = (userId: string, workspaceId: string): string =>
  `metis.lastVisit.${userId}.${workspaceId}`;

/** The previous visit's ISO timestamp, or null on the first visit (or if storage is unavailable). */
export function getLastVisit(userId: string, workspaceId: string): string | null {
  try {
    return localStorage.getItem(key(userId, workspaceId));
  } catch {
    return null;
  }
}

/** Record this visit so the next return measures the digest window from here. */
export function markVisited(userId: string, workspaceId: string, at: string): void {
  try {
    localStorage.setItem(key(userId, workspaceId), at);
  } catch {
    /* storage unavailable — the digest just won't narrow on the next visit */
  }
}
