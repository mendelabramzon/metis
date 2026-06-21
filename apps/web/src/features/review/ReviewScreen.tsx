import { useCallback, useEffect, useState } from "react";

import {
  approveInboxItem,
  listApprovals,
  listContradictions,
  reviewContradiction,
} from "@/api/client";
import type { ContradictionStatus, ContradictionView, InboxItemView } from "@/api/types";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageContainer,
  SensitivityBadge,
} from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./review.module.css";

type Filter = "pending" | "completed";

function cx(...parts: (string | false | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ContradictionCard({
  contradiction,
  onDecide,
}: {
  contradiction: ContradictionView;
  onDecide: (id: string, status: ContradictionStatus) => void;
}) {
  return (
    <Card>
      <div className={styles.itemHead}>
        <Badge variant="warning" dot>
          Contradiction
        </Badge>
        <span className={styles.itemSummary}>{contradiction.summary}</span>
      </div>
      {contradiction.explanation && <div className={styles.itemBody}>{contradiction.explanation}</div>}
      <div className={styles.itemMeta}>
        <SensitivityBadge level={contradiction.sensitivity} />
        <span>
          {contradiction.claim_ids.length} claim{contradiction.claim_ids.length === 1 ? "" : "s"}
        </span>
        {formatDate(contradiction.created_at) && <span>{formatDate(contradiction.created_at)}</span>}
        {contradiction.status !== "open" && <Badge variant="neutral">{contradiction.status}</Badge>}
      </div>
      {contradiction.status === "open" && (
        <div className={styles.itemFoot}>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onDecide(contradiction.contradiction_id, "resolved")}
          >
            Resolve
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onDecide(contradiction.contradiction_id, "dismissed")}
          >
            Dismiss
          </Button>
        </div>
      )}
    </Card>
  );
}

function ApprovalCard({ item, onApprove }: { item: InboxItemView; onApprove: () => void }) {
  return (
    <Card>
      <div className={styles.itemHead}>
        <Badge variant="info" dot>
          {item.kind === "wiki_patch" ? "Wiki patch" : "Action"}
        </Badge>
        <span className={styles.itemSummary}>{item.summary}</span>
      </div>
      <div className={styles.itemFoot}>
        <Button variant="primary" size="sm" onClick={onApprove}>
          Approve
        </Button>
      </div>
    </Card>
  );
}

/**
 * The Review queue (F1): one queue over contradictions (member-gated, per-workspace) and the
 * approval inbox (operator-gated). Pending by default; completed/dismissed behind a filter.
 * Decisions resolve from here. F2 enriches the cards with conflicting snippets + proposal diffs.
 */
export function ReviewScreen() {
  const { userBearer, activeWorkspaceId, operatorToken } = useSession();
  const [filter, setFilter] = useState<Filter>("pending");
  const [contradictions, setContradictions] = useState<ContradictionView[]>([]);
  const [approvals, setApprovals] = useState<InboxItemView[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      let cons: ContradictionView[] = [];
      if (userBearer && activeWorkspaceId) {
        if (filter === "pending") {
          cons = await listContradictions(userBearer, activeWorkspaceId, "open");
        } else {
          const [resolved, dismissed] = await Promise.all([
            listContradictions(userBearer, activeWorkspaceId, "resolved"),
            listContradictions(userBearer, activeWorkspaceId, "dismissed"),
          ]);
          cons = [...resolved, ...dismissed];
        }
      }
      const apps = filter === "pending" && operatorToken ? await listApprovals(operatorToken) : [];
      setContradictions(cons);
      setApprovals(apps);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load the review queue.");
      setStatus("error");
    }
  }, [filter, userBearer, activeWorkspaceId, operatorToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(id: string, next: ContradictionStatus) {
    if (!userBearer || !activeWorkspaceId) return;
    await reviewContradiction(userBearer, activeWorkspaceId, id, next);
    await load();
  }

  async function approve(item: InboxItemView) {
    if (!operatorToken) return;
    await approveInboxItem(operatorToken, item.kind, item.id);
    await load();
  }

  const total = contradictions.length + approvals.length;

  return (
    <PageContainer>
      <div className={styles.header}>
        <h1 className={styles.title}>Review</h1>
      </div>

      <div className={styles.filter} role="tablist" aria-label="Review filter">
        <button
          type="button"
          role="tab"
          aria-selected={filter === "pending"}
          className={cx(styles.filterBtn, filter === "pending" && styles.filterBtnOn)}
          onClick={() => setFilter("pending")}
        >
          Pending
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filter === "completed"}
          className={cx(styles.filterBtn, filter === "completed" && styles.filterBtnOn)}
          onClick={() => setFilter("completed")}
        >
          Completed
        </button>
      </div>

      {status === "loading" ? (
        <p style={{ color: "var(--color-text-muted)" }} role="status">
          Loading…
        </p>
      ) : status === "error" ? (
        <ErrorState
          title="Couldn’t load the review queue"
          description={error}
          actions={
            <Button variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : total === 0 ? (
        <EmptyState
          title={filter === "pending" ? "You’re all caught up" : "Nothing here yet"}
          description={
            filter === "pending"
              ? "No contradictions or approvals are waiting. New conflicting evidence and proposals will appear here."
              : "Resolved and dismissed items will show here once you’ve worked through the queue."
          }
        />
      ) : (
        <div className={styles.list}>
          {approvals.map((item) => (
            <ApprovalCard key={`${item.kind}-${item.id}`} item={item} onApprove={() => void approve(item)} />
          ))}
          {contradictions.map((contradiction) => (
            <ContradictionCard
              key={contradiction.contradiction_id}
              contradiction={contradiction}
              onDecide={(id, next) => void decide(id, next)}
            />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
