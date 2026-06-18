# Metis

A workspace memory/context engine: evidence-first ingestion, structured memory,
background maintenance, a compiled wiki projection, retrieval/chat, and
skill-based actions.

**Stages 0–11 are implemented**: the monorepo skeleton and machine-enforced package
boundaries (Stage 0), the `metis-protocol` contracts (Stage 1), the `metis-core` durable
substrate (Stage 2), local-first ingestion into cited evidence (Stage 3), the policy-bound
model router (Stage 4), the memory core — maintainer-time consolidation, versioned
embeddings, and hybrid memory retrieval (Stage 5), the maintainer worker — scheduled,
idempotent background jobs for contradictions, revision, refresh, foresight, and wiki-patch
proposal (Stage 6), the wiki compiler — a git-backed, claim-cited markdown projection with
the WiCER compile→evaluate→refine loop and an approval/commit flow (Stage 7), and the query
runtime — sensitivity-bounded hybrid retrieval, context packing, sufficiency-gated answering
with citation verification, and contradiction surfacing (Stage 8), and the skill runtime —
a Python skill-package format run under a manifest security contract: a subprocess sandbox,
deny-by-default permissions, approval-by-default for outbound actions, and audited artifact
capture (Stage 9), and the runtime-agent loop — a ReAct loop that classifies, retrieves, plans,
and acts: it selects skills by context, contains prompt injection behind a trusted-only control
plane (untrusted retrieved content is data, never an instruction), gates outbound actions on human
approval with resumable runs, records an inspectable execution trace, and files useful answers back
as patch proposals (Stage 10), and external connectors — IMAP/email (with thread reconstruction),
Slack, web clip, Google Drive, and calendar on a shared spine (cursors, rate limiting, retry/backoff,
ACL→sensitivity mapping) that emits the same `RawArtifact`/`NormalizedDoc` contract and replays from
recorded fixtures with no live credentials (Stage 11). See
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
eval/                evaluation harness: golden fixtures + quality comparisons (metis-eval)
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
