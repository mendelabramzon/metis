import { useCallback, useRef, useState } from "react";

import { ApiError, queryWorkspace } from "@/api/client";
import type { QueryResponse } from "@/api/types";
import { useSession } from "@/session/SessionContext";

/** The headline framing of an answer (the answered state's sub-outcome). */
export type AskOutcome = "sufficient" | "insufficient" | "conflicting" | "action_proposal";

export type AskState =
  | { kind: "idle" }
  | { kind: "asking"; question: string }
  | { kind: "answered"; question: string; response: QueryResponse; outcome: AskOutcome }
  | { kind: "blocked"; question: string; message: string }
  | { kind: "error"; question: string; message: string };

/** Conflicting evidence and pending approvals take precedence over the plain sufficiency framing. */
function deriveOutcome(response: QueryResponse): AskOutcome {
  if (response.pending_approvals.length > 0) return "action_proposal";
  if (response.disagreements.length > 0) return "conflicting";
  return response.sufficient ? "sufficient" : "insufficient";
}

interface UseAsk {
  state: AskState;
  /** Whether a question can be asked (a workspace is active and we're signed in). */
  canAsk: boolean;
  ask: (question: string) => Promise<void>;
  reset: () => void;
}

/**
 * The Ask state machine (D1). Drives the screen through idle → asking → answered (sufficient /
 * insufficient / conflicting / action-proposal) | blocked | error. A policy/sensitivity block (A4,
 * 403 `policy_blocked`) is a distinct calm state, not an error.
 */
export function useAsk(): UseAsk {
  const { userBearer, activeWorkspaceId } = useSession();
  const [state, setState] = useState<AskState>({ kind: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  const canAsk = userBearer !== null && activeWorkspaceId !== null;

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || !userBearer || !activeWorkspaceId) return;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ kind: "asking", question: text });
      try {
        const response = await queryWorkspace(
          userBearer,
          activeWorkspaceId,
          { text },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setState({ kind: "answered", question: text, response, outcome: deriveOutcome(response) });
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 403 && err.code === "policy_blocked") {
          setState({ kind: "blocked", question: text, message: err.message });
        } else {
          const message =
            err instanceof ApiError ? err.message : "Something went wrong reaching the workspace.";
          setState({ kind: "error", question: text, message });
        }
      }
    },
    [userBearer, activeWorkspaceId],
  );

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState({ kind: "idle" });
  }, []);

  return { state, canAsk, ask, reset };
}
