import { useEffect, useState } from "react";

import { getDigest } from "@/api/client";
import type { DigestView } from "@/api/types";
import { useSession } from "@/session/SessionContext";

import { getLastVisit, markVisited } from "./lastVisit";

/**
 * The "while you were away" digest for the active workspace (A7), surfaced on entry (F4).
 *
 * Returns a digest only on a *return* visit (a prior last-visit marker exists) when the maintainer
 * did meaningful work since then (non-empty highlights). The first visit just starts the clock and
 * shows nothing; errors or an undeployed endpoint degrade quietly to null. The marker advances after
 * a successful fetch, so a given change is summarised once and a same-session revisit stays quiet.
 */
export function useDigest(): DigestView | null {
  const { userBearer, activeWorkspaceId } = useSession();
  const [digest, setDigest] = useState<DigestView | null>(null);

  useEffect(() => {
    if (!userBearer || !activeWorkspaceId) {
      setDigest(null);
      return;
    }

    const since = getLastVisit(userBearer, activeWorkspaceId);
    const now = new Date().toISOString();
    if (since === null) {
      markVisited(userBearer, activeWorkspaceId, now); // first visit — nothing to report yet
      setDigest(null);
      return;
    }

    const controller = new AbortController();
    void getDigest(userBearer, activeWorkspaceId, since, controller.signal)
      .then((view) => {
        if (controller.signal.aborted) return;
        markVisited(userBearer, activeWorkspaceId, now);
        setDigest(view.highlights.length > 0 ? view : null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setDigest(null);
      });
    return () => controller.abort();
  }, [userBearer, activeWorkspaceId]);

  return digest;
}
