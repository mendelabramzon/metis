# Package Boundaries

This is the human-readable mirror of [`../../.importlinter`](../../.importlinter).
The two must stay in sync: the contract file is enforced by `make boundaries` and
the tests under `tests/architecture/`; this document explains why. The source of
truth for responsibilities is [`../package-decomposition.md`](../package-decomposition.md).

## Dependency direction

Dependencies point inward toward shared contracts. `metis-protocol` is the lowest
layer and imports no other Metis package.

```text
metis-protocol      (imports no other metis package)
      ▲
metis-core          (imports: protocol)
      ▲
  ┌───┴───────────────┐
ingestion        maintainer        runtime
(protocol, core, (protocol, core)  (protocol, core, skills)
 controlled
 skills)

metis-skills        (imports: protocol only)
```

## Allowed edges

| Package | May import | Must not import |
|---|---|---|
| `metis-protocol` | third-party only | any `metis_*` package |
| `metis-core` | `metis-protocol` | ingestion, maintainer, runtime, skills |
| `metis-ingestion` | `metis-protocol`, `metis-core`, (controlled) `metis-skills` | maintainer, runtime |
| `metis-maintainer` | `metis-protocol`, `metis-core` | ingestion, runtime, skills |
| `metis-runtime` | `metis-protocol`, `metis-core`, `metis-skills` | ingestion, maintainer |
| `metis-skills` | `metis-protocol` | core, ingestion, maintainer, runtime |

The single optional edge is **ingestion → skills**, used only in a restricted,
off-by-default ingestion-enrichment mode; it is deliberately *not* forbidden by
the contracts.

## How the contracts encode this

| Contract (`.importlinter`) | Type | Enforces |
|---|---|---|
| `protocol-independence` | forbidden | protocol imports no other `metis_*` package |
| `core-spine` | layers | `protocol < core < {ingestion \| maintainer \| runtime}` — core imports only protocol; the three producers are mutually independent |
| `skills-isolation` | forbidden | skills imports none of core/ingestion/maintainer/runtime |
| `skills-consumers` | forbidden | core and maintainer must not import skills (runtime may; ingestion may, controlled) |

## Proving enforcement

- `tests/architecture/test_import_boundaries.py` asserts all contracts hold on the
  real source tree.
- `tests/architecture/test_boundary_enforcement_negative.py` writes a probe module
  importing `metis_core` into `metis_protocol` and asserts `lint-imports` reports a
  **broken** contract — proving the guardrail catches regressions, not just that it
  is configured.
