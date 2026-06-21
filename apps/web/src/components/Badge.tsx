import type { ReactNode } from "react";

import type {
  ActionRisk,
  RoutingOutcome,
  Sensitivity,
  WorkspaceScope,
} from "@/domain/types";
import { RISK_LABELS } from "@/domain/types";

import styles from "./Badge.module.css";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "accent";

/** Every variant maps to a color-pair class in Badge.module.css; the union keeps that exhaustive. */
export type BadgeVariant =
  | BadgeTone
  | `scope-${WorkspaceScope}`
  | `sensitivity-${Sensitivity}`
  | `routing-${RoutingOutcome}`
  | `risk-${ActionRisk}`;

interface BadgeProps {
  /** A semantic tone or a domain variant key (e.g. `scope-personal`). */
  variant?: BadgeVariant;
  /** Show a leading status dot. */
  dot?: boolean;
  children: ReactNode;
}

function cx(...parts: (string | false | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/** Base badge: a small, calm pill. `variant` selects a color pair from Badge.module.css. */
export function Badge({ variant = "neutral", dot = false, children }: BadgeProps) {
  const variantClass = styles[variant] ?? styles.neutral;
  return (
    <span className={cx(styles.badge, variantClass)}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  );
}

/** Personal vs shared workspace origin (A1/D2). */
export function ScopeBadge({ scope }: { scope: WorkspaceScope }) {
  return (
    <Badge variant={`scope-${scope}`} dot>
      {scope === "personal" ? "Personal" : "Shared"}
    </Badge>
  );
}

/** Data sensitivity floor (A1/D2). Calm escalation; restricted is rose, not alarm-red. */
export function SensitivityBadge({ level }: { level: Sensitivity }) {
  const label = level.charAt(0).toUpperCase() + level.slice(1);
  return <Badge variant={`sensitivity-${level}`}>{label}</Badge>;
}

/** Where the answer was produced (A2/D5): on-device vs external model. */
export function RoutingBadge({ outcome }: { outcome: RoutingOutcome }) {
  return (
    <Badge variant={`routing-${outcome}`} dot>
      {outcome === "local" ? "On-device" : "External model"}
    </Badge>
  );
}

/** Proposed-action risk tier (D7). */
export function RiskBadge({ risk }: { risk: ActionRisk }) {
  return <Badge variant={`risk-${risk}`}>{RISK_LABELS[risk]}</Badge>;
}
