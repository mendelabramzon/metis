import type { ActionKind, ProposedActionView } from "@/api/types";
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  RiskBadge,
  SensitivityBadge,
} from "@/components";

import styles from "./ask.module.css";

const KIND_LABELS: Record<ActionKind, string> = {
  answer: "Answer",
  find_evidence: "Find evidence",
  inspect_source: "Inspect source",
  draft_response: "Draft response",
  create_memory: "Create memory",
  create_wiki_patch: "Update the wiki",
  start_sync: "Sync a source",
  propose_source_change: "Change a source",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

/**
 * A proposed-action card (D7): what the system understood, its risk tier, the target parameters,
 * and the recorded decision controls. Effectful actions are explicit and approval-gated — Approve
 * runs the dispatch; Reject drops it. (Read-only never reaches here; it answers directly.)
 */
export function ActionCard({
  action,
  busy,
  onApprove,
  onReject,
}: {
  action: ProposedActionView;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const params = Object.entries(action.parameters);
  return (
    <Card>
      <CardHeader title={KIND_LABELS[action.kind]}>
        <RiskBadge risk={action.risk} />
        <SensitivityBadge level={action.sensitivity} />
      </CardHeader>
      <CardBody>{action.summary}</CardBody>
      {params.length > 0 && (
        <div className={styles.paramList}>
          {params.map(([key, value]) => (
            <div key={key} className={styles.paramRow}>
              <span>{key}</span>
              <code>{formatValue(value)}</code>
            </div>
          ))}
        </div>
      )}
      <CardFooter>
        <Button variant="primary" onClick={onApprove} disabled={busy}>
          {busy ? "Running…" : "Approve & run"}
        </Button>
        <Button variant="secondary" onClick={onReject} disabled={busy}>
          Reject
        </Button>
      </CardFooter>
    </Card>
  );
}
