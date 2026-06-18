# ADR 0003: Import-boundary enforcement — import-linter

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

The architecture depends on a strict dependency DAG (see
[`../architecture/package-boundaries.md`](../architecture/package-boundaries.md)):
`metis-protocol` imports nothing else; `metis-core` imports only protocol; the
producers depend inward; `metis-skills` may import only protocol. These rules must
fail CI before a bad import spreads, not be left to review.

## Decision

Encode the DAG in **import-linter** contracts in [`../../.importlinter`](../../.importlinter)
and run them via `make boundaries` (`lint-imports`). Contracts used:

- a **forbidden** contract making `metis-protocol` independent of all other
  `metis_*` packages;
- a **layers** contract for the spine `protocol < core < {ingestion | maintainer | runtime}`;
- **forbidden** contracts isolating `metis-skills` (imports only protocol) and
  restricting who may import skills (runtime, plus controlled ingestion).

Enforcement is proven by two tests under `tests/architecture/`: a positive test
asserting all contracts hold, and a **negative test** that drops a probe module
importing `metis_core` into `metis_protocol` and asserts `lint-imports` reports a
broken contract.

## Consequences

- Boundary regressions fail `make check` and CI deterministically.
- The contract file is the executable mirror of the human-readable boundaries doc;
  both must be updated together.
- The negative test guarantees the guardrail catches regressions rather than
  silently passing.

## Alternatives considered

- **tach** (Rust): newer, fast, similar semantics — revisit if graph build time
  becomes a bottleneck at scale.
- **Hand-rolled AST checks**: more code to maintain, less declarative, easy to get
  subtly wrong.
