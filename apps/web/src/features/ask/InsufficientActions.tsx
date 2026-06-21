import { useNavigate } from "react-router-dom";

import { Button } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./ask.module.css";

/**
 * Inline next actions for an insufficient-evidence answer (D3 + H4): add context rather than hit a
 * dead end. Upload/connect route to Sources; "broaden scope" widens the query lens when a shared
 * workspace is available; "try again" re-asks (the still-backfilling case — a just-connected source
 * may still be importing). No numeric confidence score — an honest "not enough yet" + a way out.
 */
export function InsufficientActions({ onRetry }: { onRetry: () => void }) {
  const navigate = useNavigate();
  const { scope, setScope, workspaces } = useSession();
  const canBroaden = scope === "personal" && workspaces.some((w) => w.kind === "shared");

  return (
    <div className={styles.nextActions}>
      <p className={styles.nextLead}>
        Add more context, then ask again. Just connected a source? It may still be importing — give
        it a moment and try again.
      </p>
      <div className={styles.nextButtons}>
        <Button variant="primary" onClick={() => navigate("/sources")}>
          Upload documents
        </Button>
        <Button variant="secondary" onClick={() => navigate("/sources")}>
          Connect a source
        </Button>
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
        {canBroaden && (
          <Button variant="secondary" onClick={() => setScope("mixed")}>
            Broaden to mixed scope
          </Button>
        )}
      </div>
    </div>
  );
}
