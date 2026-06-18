# ADR 0002: Test framework — pytest

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

The system needs unit, contract, property, and (later) async tests, runnable as a
single suite from the repo root across many workspace members whose test files
share names (`test_smoke.py`, `test_boot.py`).

## Decision

Use **pytest** with **pytest-cov**, **hypothesis** (property tests for
schema/round-trip invariants in later stages), and **pytest-asyncio** (async I/O
interfaces, ADR 0008). Configuration lives in the root `pyproject.toml`
`[tool.pytest.ini_options]`: `testpaths = [tests, packages, services]`,
`--strict-markers --strict-config`, `asyncio_mode = auto`, and
**`--import-mode=importlib`** so same-named test modules coexist without
`__init__.py` shims or `sys.path` collisions.

## Consequences

- One `uv run pytest` (or `make test`) runs everything from the root.
- importlib mode means test modules are imported by path under unique names;
  shared helpers are exposed via `conftest.py` fixtures rather than direct imports.
- `--strict-config` turns unknown ini keys into errors, catching config drift.

## Alternatives considered

- **unittest**: stdlib-only, but no fixtures/parametrization ergonomics, no
  property testing, weaker plugin ecosystem.
