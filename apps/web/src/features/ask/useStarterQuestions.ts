import { useEffect, useState } from "react";

import { getStarterQuestions } from "@/api/client";
import { useSession } from "@/session/SessionContext";

/**
 * Grounded starter questions for the active workspace (A5), for the onboarding idle state (H3).
 * Empty when the workspace has no evidence yet, or when the endpoint isn't deployed — either way
 * the Ask screen falls back to the add-a-source guidance, so this degrades quietly.
 */
export function useStarterQuestions(): string[] {
  const { userBearer, activeWorkspaceId } = useSession();
  const [questions, setQuestions] = useState<string[]>([]);

  useEffect(() => {
    if (!userBearer || !activeWorkspaceId) {
      setQuestions([]);
      return;
    }
    const controller = new AbortController();
    void getStarterQuestions(userBearer, activeWorkspaceId, controller.signal)
      .then((view) => {
        if (!controller.signal.aborted) setQuestions(view.questions);
      })
      .catch(() => {
        if (!controller.signal.aborted) setQuestions([]);
      });
    return () => controller.abort();
  }, [userBearer, activeWorkspaceId]);

  return questions;
}
