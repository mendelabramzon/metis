import { useCallback, useEffect, useState } from "react";

import { listSources } from "@/api/client";
import type { SourceView } from "@/api/types";
import { SensitivityBadge } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

/**
 * Permissions & sensitivity (G3). Sensitivity is a floor set at creation — a workspace's default
 * and each source's tier (private connectors default more restrictive). The gateway has no
 * sensitivity-update endpoint yet, so this is a read-only overview; editing is a backend follow-up.
 */
export function PermissionsSection() {
  const { operatorToken, activeWorkspace, activeWorkspaceId } = useSession();
  const [sources, setSources] = useState<SourceView[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!operatorToken || !activeWorkspaceId) {
      setLoaded(true);
      return;
    }
    try {
      const all = await listSources(operatorToken);
      setSources(all.filter((s) => s.workspace_id === activeWorkspaceId));
    } catch {
      /* the note below covers the no-operator-access case */
    } finally {
      setLoaded(true);
    }
  }, [operatorToken, activeWorkspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <SectionHeader
        title="Permissions"
        lede="Sensitivity is the floor on where a workspace’s data can go. It’s set when a workspace or source is created — a private connector defaults to a more restrictive tier."
      />

      {activeWorkspace && (
        <div className={styles.field}>
          <span className={styles.label}>Workspace default sensitivity</span>
          <span>
            <SensitivityBadge level={activeWorkspace.defaultSensitivity} />
          </span>
        </div>
      )}

      <h3 className={styles.label} style={{ marginTop: "var(--space-5)" }}>
        Source sensitivity
      </h3>
      {!operatorToken ? (
        <div className={styles.note}>
          Per-source sensitivity needs operator access to read the source list.
        </div>
      ) : !loaded ? (
        <p className={styles.value} role="status">
          Loading…
        </p>
      ) : sources.length === 0 ? (
        <p className={styles.value}>No sources in this workspace yet.</p>
      ) : (
        sources.map((source) => (
          <div key={source.id} className={styles.row}>
            <div className={styles.rowMain}>
              <div className={styles.rowTitle}>{source.name}</div>
              <div className={styles.rowMeta}>{source.connector}</div>
            </div>
            <span className={styles.rowSpacer} />
            <SensitivityBadge level={source.sensitivity} />
          </div>
        ))
      )}

      <div className={styles.note}>
        Changing a workspace or source sensitivity after creation isn’t available yet — the gateway
        has no sensitivity-update endpoint (a backend follow-up).
      </div>
    </>
  );
}
