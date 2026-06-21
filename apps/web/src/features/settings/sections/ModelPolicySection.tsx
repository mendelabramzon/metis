import { useCallback, useEffect, useState } from "react";

import { getModelPolicy, getSpend, setModelPolicy } from "@/api/client";
import type { SpendView } from "@/api/types";
import { Button, ErrorState } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

/**
 * Model policy + spend (G4). The external-models toggle and daily cap feed the router's pre-prompt
 * allowlist — they're enforced server-side, never overridable per answer. Spend is read-only.
 */
export function ModelPolicySection() {
  const { userBearer, activeWorkspaceId } = useSession();
  const [allowExternal, setAllowExternal] = useState(true);
  const [cap, setCap] = useState("");
  const [spend, setSpend] = useState<SpendView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userBearer || !activeWorkspaceId) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      const policy = await getModelPolicy(userBearer, activeWorkspaceId);
      setAllowExternal(policy.allow_external_models);
      setCap(policy.daily_cost_cap_usd == null ? "" : String(policy.daily_cost_cap_usd));
      // Spend is admin-gated; tolerate a 403 for non-admins by leaving it null.
      setSpend(await getSpend(userBearer, activeWorkspaceId).catch(() => null));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load model policy.");
      setStatus("error");
    }
  }, [userBearer, activeWorkspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (!userBearer || !activeWorkspaceId) return;
    const trimmed = cap.trim();
    const capValue = trimmed === "" ? null : Number(trimmed);
    if (capValue !== null && (Number.isNaN(capValue) || capValue < 0)) {
      setError("Enter a valid daily cap, or leave it blank for no cap.");
      return;
    }
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await setModelPolicy(userBearer, activeWorkspaceId, {
        allow_external_models: allowExternal,
        daily_cost_cap_usd: capValue,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t save. You may need admin access.");
    } finally {
      setBusy(false);
    }
  }

  if (status === "error") {
    return (
      <>
        <SectionHeader title="Model policy" />
        <ErrorState
          title="Couldn’t load model policy"
          description={error}
          actions={
            <Button variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      </>
    );
  }

  const byTask = spend ? Object.entries(spend.today_by_task) : [];

  return (
    <>
      <SectionHeader
        title="Model policy"
        lede="These feed the router’s pre-prompt allowlist. They’re enforced server-side and can’t be overridden on a single answer."
      />

      <label className={styles.toggle}>
        <input
          type="checkbox"
          checked={allowExternal}
          onChange={(e) => {
            setAllowExternal(e.target.checked);
            setSaved(false);
          }}
        />
        <span className={styles.toggleText}>Allow external models</span>
      </label>
      <p className={styles.toggleHint} style={{ marginLeft: "1.45rem", maxWidth: "30rem" }}>
        When off, this workspace’s data never leaves for an external provider — restricted evidence
        is answered on-device.
      </p>

      <div className={styles.field} style={{ marginTop: "var(--space-4)" }}>
        <span className={styles.label}>Daily spend cap (USD)</span>
        <input
          className={styles.control}
          inputMode="decimal"
          placeholder="No cap"
          value={cap}
          onChange={(e) => {
            setCap(e.target.value);
            setSaved(false);
          }}
        />
      </div>

      <div className={styles.actions}>
        <Button variant="primary" onClick={() => void save()} disabled={busy}>
          {busy ? "Saving…" : "Save policy"}
        </Button>
        {saved && <span className={styles.saved}>Saved</span>}
      </div>
      {error && <div className={styles.error}>{error}</div>}

      <h3 className={styles.label} style={{ marginTop: "var(--space-6)" }}>
        Spend today
      </h3>
      {spend == null ? (
        <p className={styles.value}>Spend needs admin access to view.</p>
      ) : (
        <>
          <div className={styles.spendTotal}>${spend.today_total_usd.toFixed(4)}</div>
          {byTask.length === 0 ? (
            <p className={styles.value}>No model spend yet today.</p>
          ) : (
            byTask.map(([task, usd]) => (
              <div key={task} className={styles.spendRow}>
                <span className={styles.spendTask}>{task}</span>
                <span>${usd.toFixed(4)}</span>
              </div>
            ))
          )}
        </>
      )}
    </>
  );
}
