import { useCallback, useRef, useState } from "react";

import {
  ApiError,
  approveAction,
  executeAction,
  proposeAction,
  queryWorkspace,
  rejectAction,
} from "@/api/client";
import type { ActionExecutionView, ProposedActionView, QueryResponse } from "@/api/types";
import { useSession } from "@/session/SessionContext";

/** The headline framing of an answer (the answered state's sub-outcome). */
export type AskOutcome = "sufficient" | "insufficient" | "conflicting" | "action_proposal";

export type AskState =
  | { kind: "idle" }
  | { kind: "asking"; question: string }
  | { kind: "answered"; question: string; response: QueryResponse; outcome: AskOutcome }
  | { kind: "action"; question: string; action: ProposedActionView }
  | { kind: "executing"; question: string; action: ProposedActionView }
  | { kind: "executed"; question: string; result: ActionExecutionView }
  | { kind: "blocked"; question: string; message: string; reason: "policy" | "external" }
  | { kind: "error"; question: string; message: string };

/** Conflicting evidence and pending approvals take precedence over the plain sufficiency framing. */
function deriveOutcome(response: QueryResponse): AskOutcome {
  if (response.pending_approvals.length > 0) return "action_proposal";
  if (response.disagreements.length > 0) return "conflicting";
  return response.sufficient ? "sufficient" : "insufficient";
}

interface UseAsk {
  state: AskState;
  canAsk: boolean;
  ask: (question: string) => Promise<void>;
  /** Approve+execute (true) or reject (false) the proposed action in the current `action` state. */
  decideAction: (approve: boolean) => Promise<void>;
  reset: () => void;
}

/**
 * The Ask state machine (D1) with the operator-gated command merge (D7). Without the operator
 * principal, input goes straight to the grounded `/query` path. With it, input is first interpreted
 * via `/actions`: read-only routes back to `/query` (keeping the rich A1 citations), an EXTERNAL
 * action is blocked, and an effectful action surfaces a card for approve→execute / reject.
 */
export function useAsk(): UseAsk {
  const { userBearer, activeWorkspaceId, operatorToken } = useSession();
  const [state, setState] = useState<AskState>({ kind: "idle" });
  const stateRef = useRef<AskState>(state);
  stateRef.current = state;
  const controllerRef = useRef<AbortController | null>(null);
  const canAsk = userBearer !== null && activeWorkspaceId !== null;

  const runQuery = useCallback(
    async (bearer: string, workspaceId: string, text: string, signal: AbortSignal) => {
      try {
        const response = await queryWorkspace(bearer, workspaceId, { text }, signal);
        if (signal.aborted) return;
        setState({ kind: "answered", question: text, response, outcome: deriveOutcome(response) });
      } catch (err) {
        if (signal.aborted) return;
        if (err instanceof ApiError && err.status === 403 && err.code === "policy_blocked") {
          setState({ kind: "blocked", question: text, message: err.message, reason: "policy" });
        } else {
          const message =
            err instanceof ApiError ? err.message : "Something went wrong reaching the workspace.";
          setState({ kind: "error", question: text, message });
        }
      }
    },
    [],
  );

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || !userBearer || !activeWorkspaceId) return;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ kind: "asking", question: text });

      // Operator-gated merge: interpret the input first, then route by the action's risk tier.
      if (operatorToken) {
        try {
          const action = await proposeAction(
            operatorToken,
            text,
            activeWorkspaceId,
            controller.signal,
          );
          if (controller.signal.aborted) return;
          if (action.risk === "external") {
            setState({
              kind: "blocked",
              question: text,
              message:
                "This would take an external action, which Metis won’t do automatically.",
              reason: "external",
            });
            return;
          }
          if (action.risk !== "read_only") {
            setState({ kind: "action", question: text, action });
            return;
          }
          // read-only → fall through to the grounded query for the rich, cited answer.
        } catch {
          if (controller.signal.aborted) return;
          // Interpretation failed (flaky model / bad token) — treat the input as a plain question.
        }
      }

      await runQuery(userBearer, activeWorkspaceId, text, controller.signal);
    },
    [userBearer, activeWorkspaceId, operatorToken, runQuery],
  );

  const decideAction = useCallback(
    async (approve: boolean) => {
      const current = stateRef.current;
      if (current.kind !== "action" || !operatorToken) return;
      const { question, action } = current;
      if (!approve) {
        try {
          await rejectAction(operatorToken, action.id, "rejected from Ask");
        } catch {
          /* best-effort; the proposal is dropped from the UI regardless */
        }
        setState({ kind: "idle" });
        return;
      }
      setState({ kind: "executing", question, action });
      try {
        await approveAction(operatorToken, action.id, "approved from Ask");
        const result = await executeAction(operatorToken, action.id);
        setState({ kind: "executed", question, result });
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Couldn’t run this action.";
        setState({ kind: "error", question, message });
      }
    },
    [operatorToken],
  );

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState({ kind: "idle" });
  }, []);

  return { state, canAsk, ask, decideAction, reset };
}
