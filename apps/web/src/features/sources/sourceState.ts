import type { SourceView } from "@/api/types";
import type { BadgeVariant } from "@/components/Badge";

/** The source-status vocabulary the cards can render. */
export type SourceState =
  | "connected"
  | "syncing"
  | "needs_reauth"
  | "awaiting_login"
  | "parse_warning"
  | "failed";

export type SourceHealth = "healthy" | "syncing" | "attention";

export const SOURCE_STATE_META: Record<
  SourceState,
  { label: string; variant: BadgeVariant; health: SourceHealth }
> = {
  connected: { label: "Connected", variant: "success", health: "healthy" },
  syncing: { label: "Syncing", variant: "info", health: "syncing" },
  needs_reauth: { label: "Needs re-auth", variant: "warning", health: "attention" },
  awaiting_login: { label: "Awaiting login", variant: "warning", health: "attention" },
  parse_warning: { label: "Parse warnings", variant: "warning", health: "attention" },
  failed: { label: "Failed", variant: "danger", health: "attention" },
};

/**
 * Derive a source's state. The gateway's `SourceView` carries no run-state field yet, so a
 * registered source reads as "connected"; the card renders the richer states the moment the
 * backend exposes them (a clean follow-up — last-run status on `SourceView`). Forward-compatible:
 * honors a `state` field if one appears.
 */
export function sourceState(source: SourceView): SourceState {
  const maybe = (source as { state?: string }).state;
  if (maybe && Object.prototype.hasOwnProperty.call(SOURCE_STATE_META, maybe)) {
    return maybe as SourceState;
  }
  return "connected";
}

export interface HealthSummary {
  healthy: number;
  syncing: number;
  attention: number;
}

export function summarize(sources: SourceView[]): HealthSummary {
  const summary: HealthSummary = { healthy: 0, syncing: 0, attention: 0 };
  for (const source of sources) summary[SOURCE_STATE_META[sourceState(source)].health] += 1;
  return summary;
}
