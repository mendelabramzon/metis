import { useCallback, useEffect, useState } from "react";

import { listAudit } from "@/api/client";
import type { AuditView } from "@/api/types";
import { Button, Drawer, EmptyState, ErrorState, PageContainer } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./activity.module.css";

type Filter = "mine" | "all";

function cx(...parts: (string | false | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// Audit `action` strings translated to everyday language; unknown ones get a tidy fallback.
const ACTION_LABELS: Record<string, string> = {
  "model.call": "Asked a model",
  "action.proposed": "Proposed an action",
  "action.executed": "Ran an action",
  "action.approved": "Approved an action",
  "skill.run": "Ran a skill",
  "wiki.patch.proposed": "Proposed a wiki change",
  "source.sync": "Synced a source",
  "user.provisioned": "Joined a workspace",
};

function humanizeAction(action: string): string {
  return ACTION_LABELS[action] ?? action.replace(/[._]/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Earlier";
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

function timeLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function EventDetail({ event }: { event: AuditView }) {
  const rows: [string, string][] = [
    ["Action", humanizeAction(event.action)],
    ["Actor", event.actor],
    ["When", new Date(event.occurred_at).toLocaleString()],
  ];
  if (event.target_kind) {
    rows.push(["Target", `${event.target_kind}${event.target_id ? ` · ${event.target_id}` : ""}`]);
  }
  if (event.sensitivity) rows.push(["Sensitivity", event.sensitivity]);

  return (
    <div>
      {rows.map(([key, value]) => (
        <div key={key} className={styles.detailRow}>
          <span className={styles.detailKey}>{key}</span>
          <span className={styles.detailVal}>{value}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * The Activity timeline (F3): the audit/event log grouped by day, translated to user language, with
 * an event-detail drawer. The audit endpoint is operator-scoped and global (no per-user/workspace
 * field), so this is gated on the operator principal and offers a best-effort "My actions" filter
 * (actor = me). A proper identity-gated, workspace-scoped activity feed is a backend follow-up.
 */
export function ActivityScreen() {
  const { operatorToken, user } = useSession();
  const [events, setEvents] = useState<AuditView[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  // Default to "all": the audit attributes events to agents/operators, not users, so "mine" is
  // empty until a user-attributed activity feed exists (backend follow-up).
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<AuditView | null>(null);

  const load = useCallback(async () => {
    if (!operatorToken) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      setEvents(await listAudit(operatorToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load activity.");
      setStatus("error");
    }
  }, [operatorToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = filter === "mine" && user ? events.filter((e) => e.actor === user.id) : events;
  const groups: { label: string; items: AuditView[] }[] = [];
  for (const event of visible) {
    const label = dayLabel(event.occurred_at);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(event);
    else groups.push({ label, items: [event] });
  }

  return (
    <PageContainer>
      <div className={styles.header}>
        <h1 className={styles.title}>Activity</h1>
      </div>

      {operatorToken && (
        <div className={styles.filter} role="tablist" aria-label="Activity filter">
          <button
            type="button"
            role="tab"
            aria-selected={filter === "mine"}
            className={cx(styles.filterBtn, filter === "mine" && styles.filterBtnOn)}
            onClick={() => setFilter("mine")}
          >
            My actions
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={filter === "all"}
            className={cx(styles.filterBtn, filter === "all" && styles.filterBtnOn)}
            onClick={() => setFilter("all")}
          >
            All activity
          </button>
        </div>
      )}

      {!operatorToken ? (
        <EmptyState
          title="Activity needs operator access"
          description="The audit feed is operator-scoped today. A per-user activity timeline — your actions in workspaces you can access — is a backend follow-up."
        />
      ) : status === "loading" ? (
        <p style={{ color: "var(--color-text-muted)" }} role="status">
          Loading…
        </p>
      ) : status === "error" ? (
        <ErrorState
          title="Couldn’t load activity"
          description={error}
          actions={
            <Button variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          title={filter === "mine" ? "No activity by you yet" : "No activity yet"}
          description={
            filter === "mine"
              ? "When you ask questions, add sources, or make decisions, they’ll show up here."
              : "Events will appear here as the workspace is used."
          }
          actions={
            filter === "mine" && events.length > 0 ? (
              <Button variant="secondary" onClick={() => setFilter("all")}>
                Show all activity
              </Button>
            ) : undefined
          }
        />
      ) : (
        groups.map((group, gi) => (
          <div key={`${group.label}-${gi}`} className={styles.dayGroup}>
            <div className={styles.dayLabel}>{group.label}</div>
            <div className={styles.events}>
              {group.items.map((event) => (
                <button
                  key={event.id}
                  type="button"
                  className={styles.event}
                  onClick={() => setSelected(event)}
                >
                  <span>
                    <span className={styles.eventAction}>{humanizeAction(event.action)}</span>{" "}
                    <span className={styles.eventActor}>· {event.actor}</span>
                  </span>
                  <span className={styles.eventSpacer} />
                  <span className={styles.eventTime}>{timeLabel(event.occurred_at)}</span>
                </button>
              ))}
            </div>
          </div>
        ))
      )}

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title="Event">
        {selected && <EventDetail event={selected} />}
      </Drawer>
    </PageContainer>
  );
}
