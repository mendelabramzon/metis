# ADR 0005: Type checking — mypy --strict

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Metis is contract-heavy: protocol schemas, typed interfaces (`Protocol`s), and
typed references flow across package boundaries. Strict, battle-tested type
checking catches contract drift early. Type information must propagate to
consumers of each package.

## Decision

**mypy `--strict`** is the CI type gate. Every package and service ships a
`py.typed` marker so types propagate. Config in [`../../mypy.ini`](../../mypy.ini)
uses `explicit_package_bases` + `mypy_path` over each `src/` directory (robust
against editable-install resolution), the `pydantic.mypy` plugin, and
`python_version = 3.12`. `make typecheck` runs mypy over all package/service
source. pyright is fine for local/IDE use but is not the gate.

## Consequences

- Type errors fail `make check` and CI.
- `make typecheck` covers package/service source, not tests; when tests join the
  gate in a later stage, add overrides for untyped tooling (import-linter, grimp).
- If `Protocol` variance friction appears, pyright may be promoted to (or added
  alongside) the gate; this ADR is the place to record that change.

## Alternatives considered

- **pyright-only**: excellent inference, but mypy's strict mode and plugin
  ecosystem (pydantic) are the chosen baseline; the two disagree on edge cases, so
  we pin one as the gate.
- **ty** and other newer checkers: too new to gate CI on in 2026.
