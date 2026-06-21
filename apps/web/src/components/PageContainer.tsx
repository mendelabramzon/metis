import type { ReactNode } from "react";

import styles from "./PageContainer.module.css";

/** The default scrollable, centered, padded page body that fills the shell's content area. */
export function PageContainer({ wide = false, children }: { wide?: boolean; children: ReactNode }) {
  return (
    <div className={wide ? `${styles.scroll} ${styles.wide}` : styles.scroll}>
      <div className={styles.inner}>{children}</div>
    </div>
  );
}
