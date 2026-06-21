import type { ReactNode } from "react";

import { EmptyState, PageContainer } from "@/components";

import styles from "./SectionPlaceholder.module.css";

interface SectionPlaceholderProps {
  title: string;
  lede: string;
  /** Which milestone/epic fills this section in. */
  comingIn: string;
  children?: ReactNode;
}

/**
 * A titled section header with a calm empty state. Each of the five sections renders one of these
 * in B2; the corresponding epic (D Ask, E Sources, F Review/Activity, G Settings) replaces the body.
 */
export function SectionPlaceholder({ title, lede, comingIn, children }: SectionPlaceholderProps) {
  return (
    <PageContainer>
      <section aria-labelledby="section-title">
        <h1 id="section-title" className={styles.title}>
          {title}
        </h1>
        <p className={styles.lede}>{lede}</p>
        {children ?? (
          <EmptyState
            title={`${title} arrives in ${comingIn}`}
            description="The app shell, navigation, and role-based access are in place. This section's content lands with its epic."
          />
        )}
      </section>
    </PageContainer>
  );
}
