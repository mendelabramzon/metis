import type { ReactNode } from "react";

import styles from "./StatePanel.module.css";

function cx(...parts: (string | false | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

interface StatePanelProps {
  glyph?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** Inline next-action buttons/links. */
  actions?: ReactNode;
  tone?: "empty" | "blocked" | "error";
  /** `status` for blocked/error (announced), `region` for empty. */
  role?: "status" | "region" | "alert";
}

/**
 * The shared non-content state surface. Three semantic wrappers below pin tone + a11y role so
 * call sites read clearly. Every variant leads with a next action, not a dead end (H4).
 */
export function StatePanel({
  glyph,
  title,
  description,
  actions,
  tone = "empty",
  role = "status",
}: StatePanelProps) {
  const toneClass = tone === "blocked" ? styles.blocked : tone === "error" ? styles.error : undefined;
  return (
    <div className={cx(styles.panel, toneClass)} role={role}>
      {glyph != null && (
        <span className={styles.glyph} aria-hidden="true">
          {glyph}
        </span>
      )}
      <span className={styles.title}>{title}</span>
      {description != null && <div className={styles.description}>{description}</div>}
      {actions != null && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}

type WrapperProps = Omit<StatePanelProps, "tone" | "role">;

/** Nothing here yet — points at how to add content. */
export function EmptyState(props: WrapperProps) {
  return <StatePanel tone="empty" role="region" glyph={props.glyph ?? "○"} {...props} />;
}

/** Something failed — a real error, distinct from a policy block. */
export function ErrorState(props: WrapperProps) {
  return <StatePanel tone="error" role="alert" glyph={props.glyph ?? "!"} {...props} />;
}

/** Policy/sensitivity held the request back (D6). Calm, explained, with a next step — not an error. */
export function BlockedState(props: WrapperProps) {
  return <StatePanel tone="blocked" role="status" glyph={props.glyph ?? "⛉"} {...props} />;
}
