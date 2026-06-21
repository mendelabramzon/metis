import type { ReactNode } from "react";

import styles from "./Card.module.css";

function cx(...parts: (string | false | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

interface CardProps {
  /** Tighter radius + padding for dense lists. */
  compact?: boolean;
  /** Drop the default inner padding (e.g. when composing custom regions). */
  flush?: boolean;
  className?: string;
  children: ReactNode;
}

/** A calm, compact surface. The default container for evidence, sources, review items, etc. */
export function Card({ compact = false, flush = false, className, children }: CardProps) {
  return (
    <div
      className={cx(styles.card, compact && styles.compact, !flush && styles.padded, className)}
    >
      {children}
    </div>
  );
}

interface CardButtonProps extends CardProps {
  onClick: () => void;
  /** Accessible label when the visible content isn't self-describing. */
  ariaLabel?: string;
}

/** A whole card that is itself a button (e.g. a selectable list row). Keyboard-operable. */
export function CardButton({
  compact = false,
  flush = false,
  className,
  onClick,
  ariaLabel,
  children,
}: CardButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      className={cx(
        styles.card,
        styles.interactive,
        compact && styles.compact,
        !flush && styles.padded,
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Header row: title on the left, a spacer, then trailing badges/actions. */
export function CardHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className={styles.header}>
      <span className={styles.title}>{title}</span>
      <span className={styles.spacer} />
      {children}
    </div>
  );
}

export function CardBody({ children }: { children: ReactNode }) {
  return <div className={styles.body}>{children}</div>;
}

export function CardFooter({ children }: { children: ReactNode }) {
  return <div className={styles.footer}>{children}</div>;
}
