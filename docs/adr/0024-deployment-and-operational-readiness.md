# ADR 0024: Deployment and operational readiness — single-node Compose, profiles, health, backup

- Status: Accepted
- Date: 2026-06-19
- Deciders: Metis maintainers

## Context

Stage 15 makes the full system runnable and maintainable on a single node: a Docker Compose stack,
service health checks, migrations-on-deploy, local/cloud/GPU model profiles, scheduled backups,
restore documentation, an observability surface, and an operator runbook. The bar: a clean machine
can start the stack, health checks reflect real dependency health, logs/traces connect work across
services, backup/restore works, and an operator can inspect failed jobs, model spend, policy
denials, and ingestion lag. This is operationalization — no feature work, no new security mechanisms
(Stage 14), just wiring what exists into a runnable, inspectable node.

## Decision

**A new `metis-deploy` workspace member owns the wiring, not business logic.** It holds the static
infra (`docker-compose.yml`, `compose/` profile overlays, `images/` Dockerfiles, `migrate/`,
`observability/`, `backup/`, `runbook.md`) and a small Python package for the operational logic that
deserves tests: `health` (dependency-probe aggregation), `profiles` (model-profile → Stage 4
router), `backup_job` (over the Stage 14 backup), `migrations` (the production Alembic runner), and
`observability` (the metric/label catalog). It is a consumer outside the import-boundary contracts,
like `eval`.

**One Compose stack; migrations are a one-shot init step.** Postgres + MinIO come up healthy, a
one-shot `migrate` service runs Alembic to head, then the gateway and three workers start (each
`depends_on` migrate `service_completed_successfully`) — so workers never race the schema. The
gateway is now a real serving process (uvicorn, the ASGI binding deferred from Stage 12).

**Health reflects real dependency health.** Postgres (`pg_isready`), MinIO (`/minio/health/live`),
and the model runtime each carry their own Compose healthcheck, and the gateway depends on them
being healthy. `HealthChecker` folds injected probes into one `up`/`degraded`/`down` report (worst
of the parts; a probe that raises is reported unhealthy, never thrown) for a richer readiness
endpoint than a static "ok".

**Three model profiles, one routing abstraction, one residency guarantee.** `local` (CPU Ollama)
and `gpu` (local vLLM) expose only non-external providers; `cloud` adds a hosted provider in front
of a local fallback. All three build the same Stage 4 `MetisModelRouter`, so **restricted data
routes local in every profile** — switching to `cloud` never weakens data residency. Secrets
(API keys) come from the environment / the Stage 14 secret store, never a committed file; the
profile overlays fail fast (`${ANTHROPIC_API_KEY:?}`) if a required secret is absent.

**Backup is layered and consistency is documented.** The scheduled job dumps Postgres (`pg_dump`,
the canonical truth tier) and tars the wiki; object-store blobs — content-addressed and immutable —
are captured by snapshotting the MinIO volume (or the programmatic `metis_deploy.run_backup`, which
the test exercises) in the same quiet window. Restore is the Stage 14 `restore` plus `pg_restore`.

**Observability is OTLP with bounded cardinality.** The collector receives OTLP and exports
Prometheus; the dashboards chart model spend (by task class), policy denials, ingestion lag,
parse/extraction failures, and job failures. Per-artifact/per-claim labels are dropped at the
collector to avoid a cardinality blow-up; a `trace_id` stitches a unit of work across the gateway
and workers.

## Consequences

- The acceptance checks hold (Docker-free in CI): the Compose manifest is complete and correctly
  ordered (`test_clean_start`), the health aggregation reflects real probe results
  (`test_healthchecks`), and backup/restore round-trips a fixture workspace
  (`test_backup_restore_fixture`). A live `docker compose up` and the cross-service `trace_id`
  drilldown are the documented operator/manual smoke — running the full container stack in CI is out
  of budget by design.
- New deps: `uvicorn` (gateway, to serve), `metis-deploy` (the workspace member). Config wiring
  touched: workspace members, `testpaths`, the mypy/ruff source roots, and `make typecheck`.
- **Known follow-up**: the worker *services* still run their Stage-0 wire-and-exit entrypoints; the
  engine logic and the core `Worker` lease/handle loop exist, so turning each into a long-running
  lease-and-dispatch loop is a code change, not new infrastructure — the stack already defines and
  wires them. The gateway is a fully serving process.

## Alternatives considered

- **A live `docker compose up` in the CI test**: rejected for the default suite — Docker-in-Docker
  with image builds is slow and flaky; validating the manifest (all services, healthchecks,
  migration ordering) Docker-free is the right CI check, with the live smoke as an operator step.
- **A coordinated DB+blob+wiki point-in-time snapshot**: deferred — `pg_dump` + an immutable-blob
  volume snapshot + a wiki tar taken in a quiet window is simple and consistent enough for a single
  node; a coordinated snapshot is a larger operational project.
- **Per-profile routing logic**: rejected — profiles only change *which providers exist*; the Stage
  4 router (and its restricted-data block) is identical across profiles, which is exactly what keeps
  residency guarantees comparable.
- **Committing secrets in an env file**: rejected — `.env.example` documents the surface with
  placeholders; real secrets come from the environment / the Stage 14 secret store.
- **A Kubernetes / multi-node target**: out of scope by design; services are kept stateless-friendly
  so that path stays open later.
