import type { Citation } from "@/api/types";
import { CardButton, ScopeBadge, SensitivityBadge } from "@/components";

import { scopeForCitation } from "./citationScope";
import styles from "./ask.module.css";

interface IndexedCitation {
  citation: Citation;
  index: number;
}

function CitationCard({
  citation,
  index,
  onOpen,
}: {
  citation: Citation;
  index: number;
  onOpen: (citation: Citation, index: number) => void;
}) {
  const scope = scopeForCitation(citation.scope);
  return (
    <CardButton compact onClick={() => onOpen(citation, index)} ariaLabel={`Open source ${index + 1}`}>
      <div className={styles.citeCardHead}>
        <span className={styles.citeCardTitle}>Source {index + 1}</span>
        {scope && <ScopeBadge scope={scope} />}
        {citation.sensitivity && <SensitivityBadge level={citation.sensitivity} />}
      </div>
    </CardButton>
  );
}

function Grid({
  items,
  onOpen,
}: {
  items: IndexedCitation[];
  onOpen: (citation: Citation, index: number) => void;
}) {
  return (
    <div className={styles.cardGrid}>
      {items.map(({ citation, index }) => (
        <CitationCard
          key={`${citation.claim_id}-${index}`}
          citation={citation}
          index={index}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

/**
 * Citation cards under the answer (D2). Each card shows scope + sensitivity and opens the source
 * drawer. When the answer draws on both personal and shared evidence, the cards split into labeled
 * groups so a mixed-scope answer reads clearly (never silently blending the two).
 */
export function CitationCards({
  citations,
  onOpen,
}: {
  citations: Citation[];
  onOpen: (citation: Citation, index: number) => void;
}) {
  const indexed: IndexedCitation[] = citations.map((citation, index) => ({ citation, index }));
  const personal = indexed.filter((x) => x.citation.scope === "personal");
  const other = indexed.filter((x) => x.citation.scope !== "personal");
  const mixed = personal.length > 0 && other.length > 0;

  if (!mixed) return <Grid items={indexed} onOpen={onOpen} />;

  return (
    <>
      <div className={styles.groupLabel}>From your personal context</div>
      <Grid items={personal} onOpen={onOpen} />
      <div className={styles.groupLabel}>From shared context</div>
      <Grid items={other} onOpen={onOpen} />
    </>
  );
}
