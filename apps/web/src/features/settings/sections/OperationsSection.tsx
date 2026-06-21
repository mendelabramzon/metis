import { useCallback, useEffect, useState } from "react";

import { getHealth, listJobs, listProviders, retryJob } from "@/api/client";
import type { HealthView, JobState, JobView, ProviderView } from "@/api/types";
import { Badge, Button, ErrorState } from "@/components";
import type { BadgeVariant } from "@/components/Badge";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

const JOB_VARIANT: Record<JobState, BadgeVariant> = {
  pending: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  retrying: "info",
};

/**
 * Operations (G5, operator-only): a compact health dashboard, failed-job drilldown + retry, and the
 * provider (model) inventory. All operator-token gated. Audit search lives in Activity; backup/
 * restore status is a deploy-level concern not exposed over the API (noted).
 */
export function OperationsSection() {
  const { operatorToken } = useSession();
  const [health, setHealth] = useState<HealthView | null>(null);
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [jobs, setJobs] = useState<JobView[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!operatorToken) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      const [h, p, j] = await Promise.all([
        getHealth(),
        listProviders(operatorToken),
        listJobs(operatorToken),
      ]);
      setHealth(h);
      setProviders(p);
      setJobs(j);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load operations.");
      setStatus("error");
    }
  }, [operatorToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function retry(id: string) {
    if (!operatorToken) return;
    setRetryingId(id);
    try {
      await retryJob(operatorToken, id);
      setJobs(await listJobs(operatorToken));
    } catch {
      /* leaves the job as-is; a persistent failure stays visible */
    } finally {
      setRetryingId(null);
    }
  }

  if (status === "error") {
    return (
      <>
        <SectionHeader title="Operations" />
        <ErrorState
          title="Couldn’t load operations"
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

  return (
    <>
      <SectionHeader title="Operations" lede="Deployment health, jobs, and the model inventory." />

      <div className={styles.field}>
        <span className={styles.label}>Gateway health</span>
        <span>
          {health ? (
            <Badge variant={health.status === "ok" ? "success" : "danger"} dot>
              {health.status === "ok" ? "Healthy" : health.status}
            </Badge>
          ) : (
            <span className={styles.value}>—</span>
          )}
        </span>
      </div>

      <h3 className={styles.label} style={{ marginTop: "var(--space-5)" }}>
        Jobs ({jobs.length})
      </h3>
      {jobs.length === 0 ? (
        <p className={styles.value}>No background jobs.</p>
      ) : (
        jobs.map((job) => (
          <div key={job.id} className={styles.row}>
            <div className={styles.rowMain}>
              <div className={styles.rowTitle}>{job.kind}</div>
              <div className={styles.rowMeta}>
                attempts {job.attempts}
                {job.error ? ` · ${job.error}` : ""}
              </div>
            </div>
            <span className={styles.rowSpacer} />
            <Badge variant={JOB_VARIANT[job.state]} dot>
              {job.state}
            </Badge>
            {job.state === "failed" && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void retry(job.id)}
                disabled={retryingId === job.id}
              >
                {retryingId === job.id ? "Retrying…" : "Retry"}
              </Button>
            )}
          </div>
        ))
      )}

      <h3 className={styles.label} style={{ marginTop: "var(--space-5)" }}>
        Models ({providers.length})
      </h3>
      {providers.length === 0 ? (
        <p className={styles.value}>No models enabled by a capability manifest.</p>
      ) : (
        providers.map((provider) => (
          <div key={`${provider.provider}-${provider.model_id}`} className={styles.row}>
            <div className={styles.rowMain}>
              <div className={styles.rowTitle}>{provider.model_id}</div>
              <div className={styles.rowMeta}>
                {provider.provider} · {provider.kind} · {provider.context_window.toLocaleString()} ctx
                {provider.supports_tools ? " · tools" : ""}
              </div>
            </div>
            <span className={styles.rowSpacer} />
            <Badge variant="neutral">{provider.privacy_tier}</Badge>
          </div>
        ))
      )}

      <div className={styles.note}>
        Full audit search is in Activity. Backup/restore status is a deploy-level concern and isn’t
        exposed over the API.
      </div>
    </>
  );
}
