import { useNavigate } from "react-router-dom";

import type { Citation, ConflictSideView, DisagreementView } from "@/api/types";
import { Badge, Button, SensitivityBadge } from "@/components";

import styles from "./ask.module.css";

/** A disagreement side carries the same ids as a citation (minus scope) — reuse the source drawer. */
function sideToCitation(side: ConflictSideView): Citation {
  return {
    claim_id: side.claim_id,
    source_span_id: side.source_span_id,
    artifact_id: side.artifact_id,
    scope: null,
    sensitivity: side.sensitivity,
  };
}

/**
 * The "sources disagree" panel (D4). At answer time, conflicting evidence is shown side by side —
 * each side's snippet, sensitivity, and a way into its source — and the system never silently picks
 * a winner. A link opens the contradiction in Review (F1) to resolve it.
 */
export function DisagreementPanel({
  disagreements,
  onViewSource,
}: {
  disagreements: DisagreementView[];
  onViewSource: (citation: Citation, index: number) => void;
}) {
  const navigate = useNavigate();
  return (
    <>
      {disagreements.map((disagreement, di) => (
        <section key={`${disagreement.predicate}-${di}`} className={styles.disagreement}>
          <div className={styles.disagreementHead}>
            <Badge variant="warning" dot>
              Sources disagree
            </Badge>
            {disagreement.predicate && (
              <span className={styles.disagreementPredicate}>on “{disagreement.predicate}”</span>
            )}
          </div>
          <div className={styles.sides}>
            {disagreement.sides.map((side, si) => (
              <div key={`${side.claim_id}-${si}`} className={styles.side}>
                <div className={styles.sideText}>{side.text}</div>
                <div className={styles.sideFoot}>
                  {side.sensitivity && <SensitivityBadge level={side.sensitivity} />}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onViewSource(sideToCitation(side), si)}
                  >
                    View source
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <div className={styles.disagreementFoot}>
            <Button variant="secondary" size="sm" onClick={() => navigate("/review")}>
              Resolve in Review
            </Button>
          </div>
        </section>
      ))}
    </>
  );
}
