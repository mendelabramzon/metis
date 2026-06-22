import { useEffect, useState } from "react";

import { getPreferences, updatePreferences } from "@/api/client";
import { ScopeBadge, SensitivityBadge } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

const scopeForKind = (kind: string) => (kind === "personal" ? "personal" : "shared");

/** A personal preference (not workspace-scoped): the weekly-digest opt-in (A7 / H5). */
function WeeklyDigestToggle() {
  const { userBearer } = useSession();
  const [optIn, setOptIn] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!userBearer) return;
    const controller = new AbortController();
    void getPreferences(userBearer, controller.signal)
      .then((prefs) => setOptIn(prefs.weekly_digest))
      .catch(() => {
        /* leave indeterminate — the toggle just won't render until it loads */
      });
    return () => controller.abort();
  }, [userBearer]);

  if (optIn === null || !userBearer) return null;

  async function onToggle(next: boolean) {
    setSaving(true);
    setOptIn(next); // optimistic
    try {
      const prefs = await updatePreferences(userBearer!, next);
      setOptIn(prefs.weekly_digest);
    } catch {
      setOptIn(!next); // revert on failure
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <label className={styles.toggle}>
        <input
          type="checkbox"
          checked={optIn}
          disabled={saving}
          onChange={(e) => void onToggle(e.target.checked)}
        />
        <span className={styles.toggleText}>Weekly digest</span>
      </label>
      <p className={styles.toggleHint} style={{ marginLeft: "1.45rem", maxWidth: "30rem" }}>
        A quiet weekly summary of what synced, what changed, and what needs review — a personal
        preference, on by default.
      </p>
    </>
  );
}

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
      <WeeklyDigestToggle />
    </>
  );
}
