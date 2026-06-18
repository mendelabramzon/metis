# Stage 15 Detailed Plan: Deployment And Operational Readiness

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 15. Builds on Stages 0–14.

This stage makes the full system runnable and maintainable on a single node: a Docker Compose stack, service health checks, migrations on startup/deploy, local/cloud/GPU model profiles, backup jobs, restore documentation, an observability dashboard, and an operator runbook. The standard is that a clean machine can start the stack and an operator can inspect failed jobs, model spend, policy denials, and ingestion lag.

## Objective

- Build a Docker Compose stack wiring all services and dependencies.
- Implement service health checks and migrations-on-deploy.
- Provide local, cloud, and GPU-optional model profiles.
- Implement backup jobs and restore documentation.
- Provide an observability dashboard and an operator runbook.

Non-goals: feature work (done) and security mechanism implementation (Stage 14 — this stage operationalizes it via profiles/secrets wiring).

## Package Ownership

- Owns: `metis-deploy` (Compose, env profiles, migrations wiring, observability) — depends on all runtime packages, owns no business logic.
- Uses the Stage 0 service entrypoints, the Stage 2 migrations, the Stage 4 model providers (local/cloud profiles), and the Stage 14 backup/secrets.

## Concrete Files And Modules To Create

```text
deploy/
  docker-compose.yml         # full stack
  compose/
    profiles.local.yml       # local model profile (Ollama/CPU)
    profiles.cloud.yml       # cloud model profile (hosted providers)
    profiles.gpu.yml         # GPU-optional profile (vLLM)
  images/
    gateway.Dockerfile ingest-worker.Dockerfile
    maintainer-worker.Dockerfile runtime-worker.Dockerfile
  env/
    .env.example             # documented config surface
  migrate/
    entrypoint.sh            # run Alembic migrations on startup/deploy
  observability/
    otel-collector.yml       # OpenTelemetry collector config
    dashboards/              # ingestion lag, model spend, policy denials, job failures
  backup/
    backup-job.yml           # scheduled backup of DB + object store + wiki
  runbook.md                 # operator runbook (start, inspect, recover)

deploy/tests/
  test_clean_start.py        # clean machine -> stack up + health green
  test_healthchecks.py
  test_backup_restore_fixture.py
```

## Schemas And Interfaces Touched

- No protocol changes; wires service entrypoints, config (pydantic-settings), migrations, and model-provider profiles.
- Emits the observability fields/metrics defined in engineering-refs (trace_id, model spend, policy denials, ingestion lag, job failure rates) via OpenTelemetry.

## Implementation Steps

1. Author Dockerfiles for `gateway`, `ingest-worker`, `maintainer-worker`, `runtime-worker` using the Stage 0 entrypoints.
2. Write `docker-compose.yml` wiring gateway, the three workers, Postgres, object store (MinIO), model-runtime, and web-ui; document the env surface in `.env.example`.
3. Implement migrations-on-deploy (`migrate/entrypoint.sh`) running Alembic before services start.
4. Add the three model profiles (local/cloud/GPU) as Compose overlays selecting the Stage 4 provider config.
5. Configure OpenTelemetry collection and dashboards for ingestion lag, parse/extraction failure rates, model cost by task class, policy denials, and job failures.
6. Implement scheduled backup jobs (DB + object store + wiki) and write the restore documentation; reuse the Stage 14 backup/restore.
7. Write the operator runbook: start the stack, inspect failed jobs/model spend/policy denials/ingestion lag, and recover.

## Tests And Fixtures

- **Clean start** (`test_clean_start.py`): a clean machine brings the stack up with health checks green.
- **Health checks** (`test_healthchecks.py`): health checks reflect real dependency health (DB, object store, model runtime).
- **Backup/restore fixture** (`test_backup_restore_fixture.py`): backup/restore succeeds on a fixture workspace.
- Manual/operator validation: logs/traces connect jobs across services via `trace_id`.

Fixtures: a fixture workspace small enough to ingest, answer, back up, and restore within the deployment test budget.

## Acceptance Criteria

Traces to the Stage 15 "Validation" list:

- A clean machine can start the stack.
- Health checks reflect real dependency health.
- Logs/traces connect jobs across services.
- Backup/restore succeeds on a fixture workspace.
- An operator can inspect failed jobs, model spend, policy denials, and ingestion lag.

## Risks And Open Questions

- **Single-node scope**: this targets a single node by design; multi-node/orchestrated deployment (Kubernetes) is out of scope and a later concern — keep services stateless-friendly so that path stays open.
- **Migrations-on-deploy safety**: running migrations on startup races with multiple workers; gate migrations to a single init step, not per-service.
- **Model profile parity**: local vs cloud vs GPU profiles must route through the same Stage 4 abstraction so behavior is comparable; restricted-data routing must hold in every profile.
- **Backup consistency**: coordinating DB + object store + git snapshots to a consistent point (see Stage 14); document the consistency guarantee.
- **Observability cardinality**: per-artifact/per-claim trace labels can explode cardinality; choose label sets deliberately.
- **Secret injection in Compose**: secrets must come from a secure source (not committed env files); wire to the Stage 14 secret storage and keep `.env.example` free of real secrets.
