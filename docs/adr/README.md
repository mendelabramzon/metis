# Architecture Decision Records

Consequential, hard-to-reverse decisions are recorded as ADRs using the
[MADR](https://adr.github.io/madr/)-style [`template.md`](template.md). Lighter
choices (Python version, `make` as task runner, GitHub Actions as CI provider)
are recorded in the Stage 0 plan's decision table rather than as standalone ADRs.

## Process

1. Copy [`template.md`](template.md) to `NNNN-short-title.md` using the next free
   number.
2. New ADRs start at **Proposed**; set to **Accepted** when merged.
3. Do not rewrite a decided ADR. To change a decision, add a new ADR and mark the
   old one **Superseded by ADR-XXXX**.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-monorepo-and-uv-workspace.md) | Monorepo and uv workspace | Accepted |
| [0002](0002-test-framework-pytest.md) | Test framework: pytest | Accepted |
| [0003](0003-import-boundary-enforcement.md) | Import-boundary enforcement: import-linter | Accepted |
| [0004](0004-lint-format-ruff.md) | Lint + format: ruff | Accepted |
| [0005](0005-typecheck-mypy-strict.md) | Type checking: mypy --strict | Accepted |
| [0006](0006-config-pydantic-settings.md) | Config: pydantic-settings | Accepted |
| [0007](0007-id-strategy-prefixed-uuid7.md) | ID strategy: prefixed UUIDv7 | Accepted |
| [0008](0008-async-first-io-interfaces.md) | Async-first I/O interfaces | Accepted |
| [0009](0009-service-entrypoint-convention.md) | Service entrypoint convention | Accepted |
| [0010](0010-protocol-schema-versioning-and-interface-placement.md) | Protocol schema versioning and interface placement | Accepted |
