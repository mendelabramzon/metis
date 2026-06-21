import { useEffect } from "react";

import { useSession } from "@/session/SessionContext";
import { SCOPE_SELECTIONS } from "@/session/types";
import type { ScopeSelection } from "@/session/types";

import styles from "./WorkspaceControls.module.css";

const LABEL: Record<ScopeSelection, string> = {
  personal: "Personal",
  shared: "Shared",
  mixed: "Mixed",
};

function cx(...parts: (string | false | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * The Personal / Shared / Mixed query lens (B4): always visible, persisted across sessions. Shared
 * and Mixed need a shared workspace, so they disable (and the lens self-heals to Personal) until one
 * exists. M2's Ask consumes the active scope to route queries.
 */
export function ScopeSelector() {
  const { scope, setScope, workspaces } = useSession();
  const hasShared = workspaces.some((w) => w.kind === "shared");

  useEffect(() => {
    if (!hasShared && scope !== "personal") setScope("personal");
  }, [hasShared, scope, setScope]);

  return (
    <div className={styles.segmented} role="radiogroup" aria-label="Query scope">
      {SCOPE_SELECTIONS.map((option) => {
        const disabled = option !== "personal" && !hasShared;
        const active = scope === option;
        return (
          <label
            key={option}
            className={cx(
              styles.segment,
              active && styles.segmentActive,
              disabled && styles.segmentDisabled,
            )}
            {...(disabled ? { title: "Connect a shared workspace to use this scope" } : {})}
          >
            <input
              type="radio"
              name="scope"
              value={option}
              className="sr-only"
              checked={active}
              disabled={disabled}
              onChange={() => setScope(option)}
            />
            {LABEL[option]}
          </label>
        );
      })}
    </div>
  );
}
