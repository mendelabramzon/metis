# ADR 0006: Config — pydantic-settings

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Services need typed, testable configuration with a predictable layering of
defaults, dotenv files, and process environment. Configuration types should
compose with the pydantic schemas used throughout `metis-protocol`.

## Decision

Use **pydantic-settings** `BaseSettings` for service configuration. Each service
defines its own settings class with a `METIS_<SERVICE>_` env prefix and
`env_file = ".env"`. Precedence, lowest to highest, is **field defaults < `.env`
< process environment** (pydantic-settings' default source order). At Stage 0 each
service is self-contained; the shared `BaseServiceSettings` base moves into
`metis-core` in Stage 2.

## Consequences

- Settings are typed and unit-testable (override via env in tests; see each
  service's `test_boot.py`).
- A consistent env-prefix scheme avoids cross-service variable collisions.
- `.env.example` per service documents the knobs; `.env` is git-ignored.

## Alternatives considered

- **dynaconf**: powerful layering, but less type-first and doesn't reuse our
  pydantic models.
- **Raw `os.environ` parsing**: untyped, error-prone, no validation.
