# Metis operator runbook

Single-node operation of the Metis stack: start it, inspect it, recover it. Multi-node/orchestrated
deployment (Kubernetes) is out of scope by design — services are kept stateless-friendly so that path
stays open.

## Start the stack

Pick a model profile (`local` = CPU Ollama, `cloud` = hosted provider, `gpu` = local vLLM):

```bash
cp env/.env.example .env        # fill in secrets (never commit .env)
docker compose -f docker-compose.yml -f compose/profiles.local.yml up -d
```

Order is enforced by the manifest: Postgres and MinIO come up healthy, the one-shot `migrate`
service runs Alembic to head, then the gateway and the three workers start. The gateway (API +
operator console) is on `http://localhost:8000` (`/` for the console, `/health` for liveness,
`/docs` for the API).

> Migrations run **once** in the `migrate` service (workers wait on
> `service_completed_successfully`), so multiple workers never race the schema.

## Health

```bash
docker compose ps                       # per-service health column
curl -fsS http://localhost:8000/health  # gateway liveness
```

Health reflects **real dependency health**: Postgres (`pg_isready`), MinIO
(`/minio/health/live`), and — in the local/gpu profiles — the model runtime each have their own
healthcheck, and the gateway depends on them being healthy. The aggregation logic
(`metis_deploy.health.HealthChecker`) folds component probes into one `up`/`degraded`/`down` report
for a richer readiness endpoint.

## Inspect (failed jobs, model spend, policy denials, ingestion lag)

Two surfaces:

- **API / console** (`metis-gateway`): the operator console (`/`) exposes the approval inbox, the
  jobs view (inspect + retry failed jobs), and the audit/event view. `GET /jobs`, `GET /audit`,
  `GET /approvals` back them.
- **Dashboards** (OpenTelemetry → Prometheus, `otel-collector:9464`): model spend by task class,
  policy denials, ingestion lag, parse/extraction failures, and job failures — see
  `observability/dashboards/dashboards.md`. Every unit of work carries a `trace_id` that stitches a
  request across the gateway and workers; drill from a failed-job panel into its trace by `trace_id`.

Retry a failed job: `POST /jobs/{id}/retry` (or the **retry** button in the console).

## Back up and restore

Scheduled backup (run from host cron):

```bash
docker compose -f docker-compose.yml -f backup/backup-job.yml --profile backup run --rm backup
```

This writes `db.dump` (Postgres custom-format) and `wiki.tar.gz` to the `backups` volume. Capture
the **object-store blobs** by snapshotting the `miniodata` volume in the same quiet window (blobs are
content-addressed and immutable, so the snapshot is consistent). Take all three to one quiet point;
the DB dump is the canonical truth tier (ADR 0023). The programmatic path
(`metis_deploy.run_backup` → `metis_core.security.restore`) backs up/restores the blob + wiki tiers
directly and is what the test suite exercises.

Restore:

```bash
# DB
pg_restore --clean --no-owner -d "postgresql://metis:***@localhost:5432/metis" db.dump
# wiki
tar -C ./wiki -xzf wiki.tar.gz
# blobs: restore the minio volume snapshot, or metis_core.security.restore(...) for a bundle
```

## Recover

- **A service is unhealthy**: `docker compose logs <service>`; restart with
  `docker compose restart <service>`. App services restart automatically (`restart: unless-stopped`).
- **Migrations failed**: re-run the one-shot step — `docker compose up migrate` — then bring up the
  rest. It is idempotent (Alembic upgrades to head).
- **Restricted-data routing**: the Stage 4 router blocks external providers for restricted data in
  **every** profile, so switching to `cloud` never weakens data residency. Confirm denials on the
  policy-denials panel.

## Gateway backend

The gateway runs the **Postgres** backend in the stack (`METIS_GATEWAY_BACKEND=postgres`): ingest
persists raw/normalized/parsed/claims to Postgres + MinIO, consolidates into an indexed memory cell,
and answers (with citations) through the Stage 8 query engine — so data survives a restart. Run it
locally without infra by leaving `METIS_GATEWAY_BACKEND=memory` (the default), an in-process engine
that resets on restart.

## Known wiring follow-up

The worker **services** (`ingest-worker`, `maintainer-worker`, `runtime-worker`) currently run their
Stage-0 entrypoints (wire-and-exit); the engine logic lives in the packages and the core `Worker`
lease/handle loop exists, so turning each into a long-running lease-and-dispatch loop is a code
change, not new infrastructure — the Compose stack already defines and wires them. The gateway is a
fully serving uvicorn process.
