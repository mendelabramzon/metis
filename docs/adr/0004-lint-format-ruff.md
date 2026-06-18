# ADR 0004: Lint + format — ruff

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

We want fast, consistent linting and formatting with minimal tool sprawl, applied
uniformly across all workspace members.

## Decision

Use **ruff** for both linting and formatting. Configuration is centralized in
[`../../ruff.toml`](../../ruff.toml): `target-version = py312`, `line-length = 100`,
an explicit first-party list for import sorting, and a pragmatic rule set
(`E`, `W`, `F`, `I`, `UP`, `B`, `C4`, `SIM`, `PT`, `RUF`). `make lint` runs
`ruff check` plus `ruff format --check`; `make format` applies fixes.

## Consequences

- One fast tool replaces flake8 + isort + black; a single config governs the repo.
- `make lint` is non-mutating (CI-safe); `make format` is the mutating counterpart.
- The rule set is intentionally moderate at Stage 0; rules can be tightened later
  without changing tooling.

## Alternatives considered

- **black + flake8 + isort**: three tools, three configs, slower, more moving
  parts; ruff subsumes them.
