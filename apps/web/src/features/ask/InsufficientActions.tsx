import { useNavigate } from "react-router-dom";

import { Button } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./ask.module.css";

/**
 * Inline next actions for an insufficient-evidence answer (D3): add context rather than hit a dead
 * end. Upload/connect route to Sources; "broaden scope" widens the query lens when a shared
 * workspace is available. No numeric confidence score — just an honest "not enough yet" + a way out.
 */
export function InsufficientActions() {
  const navigate = useNavigate();
  const { scope, setScope, workspaces } = useSession();
  const canBroaden = scope === "personal" && workspaces.some((w) => w.kind === "shared");

  return (
    <div className={styles.nextActions}>
      <p className={styles.nextLead}>Add more context, then ask again:</p>
      <div className={styles.nextButtons}>
        <Button variant="primary" onClick={() => navigate("/sources")}>
          Upload documents
        </Button>
        <Button variant="secondary" onClick={() => navigate("/sources")}>
          Connect a source
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
