import { useNavigate } from "react-router-dom";

import { Button } from "@/components";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

/** Data & erasure (G1): where erasure lives, with the tombstone semantics spelled out. */
export function DataSection() {
  const navigate = useNavigate();
  return (
    <>
      <SectionHeader
        title="Data & erasure"
        lede="Erasing a source or document tombstones everything derived from it — claims, memory, and wiki references — so it stops appearing in answers and evidence."
      />
      <div className={styles.note}>
        Source erasure lives on the Sources screen: each source has a permanent delete that cascades
        to its artifacts. Document-level and workspace-wide erasure are operator actions handled in
        Operations.
      </div>
      <div className={styles.actions}>
        <Button variant="secondary" onClick={() => navigate("/sources")}>
          Go to Sources
        </Button>
      </div>
    </>
  );
}
