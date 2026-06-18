# Metis

A workspace memory/context engine: evidence-first ingestion, structured memory,
background maintenance, a compiled wiki projection, retrieval/chat, and
skill-based actions.

This repository is at **Stage 0**: the monorepo skeleton, shared tooling, and
machine-enforced package boundaries. No domain logic exists yet — packages ship
empty except for a version marker. See
[`docs/plans/high-level-implementation-plan.md`](docs/plans/high-level-implementation-plan.md)
for the staged roadmap and [`docs/`](docs/README.md) for the documentation index.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (workspace + packaging, ADR 0001)
- Python 3.12+ (uv will fetch it; the floor is pinned in `.python-version`)
- `make`

## Quickstart

```bash
make install   # uv sync --all-packages — installs every package + service
make check     # boundaries + lint + typecheck + tests (the one gate)
```

Individual targets: `make format`, `make lint`, `make typecheck`, `make test`,
`make boundaries`. Run `make help` for the list.

Run a service in dry-run mode (wire settings and exit without serving):

```bash
uv run python -m metis_gateway --dry-run
uv run metis-gateway --dry-run          # installed console script
```

## Layout

```text
packages/
  metis-protocol/    shared contracts: schemas, events, interfaces, policy vocabulary
  metis-core/        durable substrate: stores, audit, jobs, policy enforcement
  metis-ingestion/   evidence production: connectors, parsers, segmentation, extraction
  metis-maintainer/  memory maintenance: contradictions, consolidation, foresight, wiki patches
  metis-runtime/     user-facing intelligence: chat, retrieval, context packing, skills
  metis-skills/      reusable Python skill packages
services/
  gateway/           API surface (metis-gateway)
  ingest-worker/     ingestion jobs (metis-ingest-worker)
  maintainer-worker/ background maintenance jobs (metis-maintainer-worker)
  runtime-worker/    retrieval/agent jobs (metis-runtime-worker)
docs/                plans, ADRs, architecture, references
tests/architecture/  import-boundary enforcement (positive + negative)
```

## Package boundaries

Dependencies point inward; `metis-protocol` imports no other Metis package. The
rules are documented in
[`docs/architecture/package-boundaries.md`](docs/architecture/package-boundaries.md),
encoded in [`.importlinter`](.importlinter), and enforced by `make boundaries`
plus the tests under `tests/architecture/` (including a negative test that proves
a forbidden import is actually caught).

## License

See [`LICENSE`](LICENSE). It is currently a proprietary placeholder — pick a real
license before any external distribution.
