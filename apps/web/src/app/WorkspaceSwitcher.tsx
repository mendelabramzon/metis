import type { WorkspaceKind } from "@/api/types";
import { useSession } from "@/session/SessionContext";
import type { WorkspaceSummary } from "@/session/types";

import styles from "./WorkspaceControls.module.css";

const KIND_ORDER: readonly WorkspaceKind[] = ["personal", "shared", "external"];
const KIND_LABEL: Record<WorkspaceKind, string> = {
  personal: "Personal",
  shared: "Shared",
  external: "External",
};

/** Switch the active workspace (always visible, persisted). A native select keeps it accessible. */
export function WorkspaceSwitcher() {
  const { workspaces, activeWorkspaceId, setActiveWorkspace } = useSession();
  if (workspaces.length === 0) return null;

  const groups = KIND_ORDER.map(
    (kind) => [kind, workspaces.filter((w) => w.kind === kind)] as const,
  ).filter(([, items]) => items.length > 0);

  return (
    <select
      aria-label="Active workspace"
      className={styles.wsSelect}
      value={activeWorkspaceId ?? ""}
      onChange={(e) => setActiveWorkspace(e.target.value)}
    >
      {groups.map(([kind, items]) => (
        <optgroup key={kind} label={KIND_LABEL[kind]}>
          {items.map((w: WorkspaceSummary) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
