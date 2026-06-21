import { ScopeBadge, SensitivityBadge } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

const scopeForKind = (kind: string) => (kind === "personal" ? "personal" : "shared");

/** Workspace settings (G1): the active workspace's identity. Read-only until a rename endpoint exists. */
export function WorkspaceSection() {
  const { activeWorkspace, role } = useSession();
  if (!activeWorkspace) {
    return (
      <>
        <SectionHeader title="Workspace" />
        <p className={styles.value}>No workspace selected.</p>
      </>
    );
  }
  return (
    <>
      <SectionHeader title="Workspace" lede="Details for the workspace you have active." />
      <div className={styles.field}>
        <span className={styles.label}>Name</span>
        <span className={styles.value}>{activeWorkspace.name}</span>
      </div>
      <div className={styles.field}>
        <span className={styles.label}>Kind</span>
        <span>
          <ScopeBadge scope={scopeForKind(activeWorkspace.kind)} />
        </span>
      </div>
      <div className={styles.field}>
        <span className={styles.label}>Default sensitivity</span>
        <span>
          <SensitivityBadge level={activeWorkspace.defaultSensitivity} />
        </span>
      </div>
      <div className={styles.field}>
        <span className={styles.label}>Your role</span>
        <span className={styles.value}>{role}</span>
      </div>
    </>
  );
}
