import { useEffect, useState } from "react";

import { getClaimEvidence } from "@/api/client";
import type { ClaimEvidenceView, ContradictionStatus, ContradictionView } from "@/api/types";
import { Badge, Button, Card, SensitivityBadge } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./review.module.css";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * A contradiction card (F2): the conflicting claims are drilled to their source snippets so the
 * decision is made from evidence, not a summary. Each side shows the claim + its quoted span.
 */
export function ContradictionCard({
  contradiction,
  onDecide,
}: {
  contradiction: ContradictionView;
  onDecide: (id: string, status: ContradictionStatus) => void;
}) {
  const { userBearer, activeWorkspaceId } = useSession();
  const [claims, setClaims] = useState<ClaimEvidenceView[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!userBearer || !activeWorkspaceId || contradiction.claim_ids.length === 0) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    void Promise.all(
      contradiction.claim_ids.map((id) =>
        getClaimEvidence(userBearer, activeWorkspaceId, id, controller.signal).catch(() => null),
      ),
    ).then((results) => {
      if (controller.signal.aborted) return;
      setClaims(results.filter((c): c is ClaimEvidenceView => c !== null));
      setLoading(false);
    });
    return () => controller.abort();
  }, [contradiction.claim_ids, userBearer, activeWorkspaceId]);

  return (
    <Card>
      <div className={styles.itemHead}>
        <Badge variant="warning" dot>
          Contradiction
        </Badge>
        <span className={styles.itemSummary}>{contradiction.summary}</span>
      </div>
      {contradiction.explanation && <div className={styles.itemBody}>{contradiction.explanation}</div>}

      {loading ? (
        <div className={styles.claimLoading} role="status">
          Loading evidence…
        </div>
      ) : claims.length > 0 ? (
        <div className={styles.claims}>
          {claims.map((claim) => (
            <div key={claim.claim_id} className={styles.claimSnippet}>
              <div className={styles.claimText}>
                {claim.negated ? "Not: " : ""}
                {claim.text}
              </div>
              {claim.spans[0]?.quote && (
                <div className={styles.claimQuote}>“{claim.spans[0].quote}”</div>
              )}
            </div>
          ))}
        </div>
      ) : null}

      <div className={styles.itemMeta}>
        <SensitivityBadge level={contradiction.sensitivity} />
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
