import { useState } from "react";
import { Link } from "react-router-dom";

import { useDigest } from "./useDigest";
import styles from "./whileYouWereAway.module.css";

/**
 * A quiet "while you were away" line shown on entry (F4) when the maintainer did meaningful work
 * since the last visit — new contradictions to review, facts added to memory. Dismissible, and
 * renders nothing when there is nothing to report (the common case).
 */
export function WhileYouWereAway() {
  const digest = useDigest();
  const [dismissed, setDismissed] = useState(false);

  if (!digest || dismissed) return null;

  return (
    <aside className={styles.banner} aria-label="While you were away">
      <p className={styles.body}>
        <span className={styles.label}>While you were away</span>
        <span className={styles.summary}>{digest.highlights.join(" · ")}</span>
        {digest.new_contradictions > 0 && (
          <Link to="/review" className={styles.link} onClick={() => setDismissed(true)}>
            Review
          </Link>
        )}
      </p>
      <button
        type="button"
        className={styles.dismiss}
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
      >
        ×
      </button>
    </aside>
  );
}
