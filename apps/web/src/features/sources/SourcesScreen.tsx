import { useCallback, useEffect, useState } from "react";

import { listSources, syncSource } from "@/api/client";
import type { SourceView } from "@/api/types";
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  PageContainer,
  SensitivityBadge,
} from "@/components";
import { useSession } from "@/session/SessionContext";

import { SOURCE_STATE_META, sourceState, summarize } from "./sourceState";
import { UploadCard } from "./UploadCard";
import styles from "./sources.module.css";

function SourceCard({
  source,
  onSync,
  queued,
}: {
  source: SourceView;
  onSync: () => void;
  queued: boolean;
}) {
  const meta = SOURCE_STATE_META[sourceState(source)];
  return (
    <Card compact>
      <div className={styles.sourceHead}>
        <span className={styles.sourceName}>{source.name}</span>
        <Badge variant={meta.variant} dot>
          {meta.label}
        </Badge>
      </div>
      <div className={styles.sourceMeta}>
        <span>{source.connector}</span>
        <SensitivityBadge level={source.sensitivity} />
        <span>{source.auth_method}</span>
      </div>
      <div style={{ marginTop: "var(--space-3)" }}>
        <Button variant="secondary" size="sm" onClick={onSync} disabled={queued}>
          {queued ? "Sync queued" : "Sync now"}
        </Button>
      </div>
    </Card>
  );
}

/**
 * The Sources screen (E1). Source management (`/sources`) is scope-token gated, so the list +
 * add-source need the operator principal; upload is per-workspace (any member). Cards group by
 * workspace with a health summary; the upload dropzone leads when empty. E2 wires upload, E3 the
 * add-source catalog/OAuth, E4 Telegram.
 */
export function SourcesScreen() {
  const { operatorToken, activeWorkspace, workspaces } = useSession();
  const [sources, setSources] = useState<SourceView[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string>("");
  const [addOpen, setAddOpen] = useState(false);
  const [queued, setQueued] = useState<ReadonlySet<string>>(new Set());
  const [picked, setPicked] = useState<string[]>([]);

  const load = useCallback(async () => {
    if (!operatorToken) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      setSources(await listSources(operatorToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load sources.");
      setStatus("error");
    }
  }, [operatorToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSync(id: string) {
    if (!operatorToken) return;
    try {
      await syncSource(operatorToken, id);
      setQueued((prev) => new Set(prev).add(id));
    } catch {
      /* surfaced via the jobs/operations view; the card simply doesn't flip to queued */
    }
  }

  const workspaceName = (id: string) => workspaces.find((w) => w.id === id)?.name ?? "Other workspace";
  const grouped = Object.entries(
    sources.reduce<Record<string, SourceView[]>>((acc, s) => {
      (acc[s.workspace_id] ??= []).push(s);
      return acc;
    }, {}),
  );

  return (
    <PageContainer>
      <div className={styles.header}>
        <h1 className={styles.title}>Sources</h1>
        <span className={styles.spacer} />
        {operatorToken && (
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            Add a source
          </Button>
        )}
      </div>

      {activeWorkspace && (
        <UploadCard
          workspaceName={activeWorkspace.name}
          onFiles={(files) => setPicked(files.map((f) => f.name))}
        />
      )}
      {picked.length > 0 && (
        <div className={styles.uploadHint} style={{ marginTop: "calc(-1 * var(--space-3))" }}>
          {picked.length} file{picked.length === 1 ? "" : "s"} selected ({picked.join(", ")}) —
          upload runs in E2.
        </div>
      )}

      {!operatorToken ? (
        <EmptyState
          title="Source management needs operator access"
          description="Sign in with an operator token to connect and manage sources. You can still upload documents to this workspace above."
        />
      ) : status === "loading" ? (
        <p style={{ color: "var(--color-text-muted)" }} role="status">
          Loading sources…
        </p>
      ) : status === "error" ? (
        <ErrorState
          title="Couldn’t load sources"
          description={error}
          actions={
            <Button variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : sources.length === 0 ? (
        <EmptyState
          title="No sources yet"
          description="Connect a mailbox, drive, or chat — or upload documents above — to give your workspaces something to remember."
          actions={
            <Button variant="primary" onClick={() => setAddOpen(true)}>
              Add a source
            </Button>
          }
        />
      ) : (
        grouped.map(([workspaceId, items]) => (
          <div key={workspaceId} className={styles.group}>
            <div className={styles.groupTitle}>{workspaceName(workspaceId)}</div>
            <HealthSummary sources={items} />
            <div className={styles.sourceGrid}>
              {items.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  onSync={() => void onSync(source.id)}
                  queued={queued.has(source.id)}
                />
              ))}
            </div>
          </div>
        ))
      )}

      <Drawer open={addOpen} onClose={() => setAddOpen(false)} title="Add a source">
        <p style={{ color: "var(--color-text-secondary)" }}>
          Connector catalog, OAuth, and scope selection arrive in E3; Telegram chat selection in E4.
        </p>
      </Drawer>
    </PageContainer>
  );
}

function HealthSummary({ sources }: { sources: SourceView[] }) {
  const summary = summarize(sources);
  return (
    <div className={styles.summary}>
      <span className={styles.summaryItem}>
        <span className={styles.summaryCount}>{summary.healthy}</span>
        <span className={styles.summaryLabel}>Healthy</span>
      </span>
      <span className={styles.summaryItem}>
        <span className={styles.summaryCount}>{summary.syncing}</span>
        <span className={styles.summaryLabel}>Syncing</span>
      </span>
      <span className={styles.summaryItem}>
        <span className={styles.summaryCount}>{summary.attention}</span>
        <span className={styles.summaryLabel}>Needs attention</span>
      </span>
    </div>
  );
}
