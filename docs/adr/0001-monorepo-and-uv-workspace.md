# ADR 0001: Monorepo and uv workspace

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Metis is six libraries plus four services that share contracts (`metis-protocol`)
and a substrate (`metis-core`) and must evolve together with strict, enforceable
import boundaries. We need fast, reproducible installs of many interdependent
local packages, a single lockfile, and first-class editable cross-package
development.

## Decision

Use a single **monorepo** managed as a **uv workspace** with members under
`packages/*` and `services/*`. The repo root is a non-package workspace root
(`tool.uv.package = false`) that pins the shared dev toolchain via
`dependency-groups.dev` and declares cross-package `tool.uv.sources` as
`{ workspace = true }`. Each member builds with the **hatchling** backend from a
`src/` layout. Target Python is **3.12** (floor, pinned in `.python-version`),
tested on 3.12 and 3.13. `make install` is `uv sync --all-packages`.

## Consequences

- One `uv.lock` for the whole system; reproducible across machines and CI.
- Cross-package edits are immediately visible (editable installs); no publish loop.
- Workspace members share one environment, so dependency conflicts surface early.
- Services are workspace members, coupling their release cadence to packages —
  acceptable now (see Stage 0 risks); revisit if independent versioning is needed.
- A single repo version for now; per-package semver is a later concern.

## Alternatives considered

- **Poetry / PDM / Rye**: viable workspaces, but uv folds in Rye, is faster, and
  has first-class workspace + single-lock support. PDM is the fallback if a uv
  workspace blocker appears.
- **Multiple repos**: rejected — contract churn across `metis-protocol` would be
  painful to coordinate and boundary enforcement would weaken.
