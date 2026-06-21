/*
 * Domain vocabulary shared across the UI (B1).
 *
 * These mirror the gateway/protocol enums the trust surfaces are built on: a citation carries a
 * workspace `scope` + `sensitivity` (A1); an answer carries a routing outcome (A2); a proposed
 * action carries a `risk` label (D7). Centralizing them here keeps badge color/label mappings in
 * one place and lets later API-typed code reuse the same unions.
 */

export type WorkspaceScope = "personal" | "shared";

export type Sensitivity = "public" | "internal" | "confidential" | "restricted";

export type RoutingOutcome = "local" | "external";

/** Action risk tiers (mirrors the console's `read_only | reversible | memory_write | wiki_write | external`). */
export type ActionRisk = "read_only" | "reversible" | "memory_write" | "wiki_write" | "external";

export const SENSITIVITY_ORDER: readonly Sensitivity[] = [
  "public",
  "internal",
  "confidential",
  "restricted",
];

/** Human-facing risk labels (the four the product speaks: Read only / Updates memory / …). */
export const RISK_LABELS: Record<ActionRisk, string> = {
  read_only: "Read only",
  reversible: "Reversible",
  memory_write: "Updates memory",
  wiki_write: "Updates wiki",
  external: "External action",
};

export const ROUTING_LABELS: Record<RoutingOutcome, string> = {
  local: "Kept on-device",
  external: "Used an external model",
};
