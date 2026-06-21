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

For a public deployment, add the TLS proxy overlay (`compose/proxy.yml`): Caddy terminates HTTPS for
one domain and forwards to the gateway, which is then no longer published on `8000` directly.

```bash
METIS_DOMAIN=metis.example.com METIS_ACME_EMAIL=ops@example.com \
  docker compose -f docker-compose.yml -f compose/profiles.local.yml -f compose/proxy.yml up -d
```

Caddy auto-issues and renews a Let's Encrypt certificate for `$METIS_DOMAIN` (persisted in the
`caddy_data` volume across restarts). Leave `METIS_DOMAIN` unset for a local bring-up — it defaults
to `localhost` and Caddy serves `https://localhost` with its internal CA.

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
- **Alerts**: load `observability/alerts.yml` into the Prometheus that scrapes the collector — spend
  ceiling, job-failure rate, ingestion lag, and restore-drill freshness, with tunable thresholds.

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

Restore drill (run from host cron, after the backup):

```bash
docker compose -f docker-compose.yml -f backup/restore-drill.yml \
    --profile restore-drill run --rm restore-drill
```

A backup you have never restored is a hope, not a backup. The drill restores the newest bundle into
a **scratch** MinIO bucket + temp wiki dir (never the live stores), asserts every blob round-trips
content-addressed, and records `metis.backup.restore_drill_runs{outcome}`. The
`RestoreDrillStale` alert fires when a passing drill has not been seen for a day, so a silently
broken backup chain surfaces before it is needed.

## Recover

- **A service is unhealthy**: `docker compose logs <service>`; restart with
  `docker compose restart <service>`. App services restart automatically (`restart: unless-stopped`).
- **Migrations failed**: re-run the one-shot step — `docker compose up migrate` — then bring up the
  rest. It is idempotent (Alembic upgrades to head).
- **Restricted-data routing**: the Stage 4 router blocks external providers for restricted data in
  **every** profile, so switching to `cloud` never weakens data residency. Confirm denials on the
  policy-denials panel.
- **A service exits with "Illegal instruction" (SIGILL) on startup**: OpenSSL's ARM crypto-extension
  detection misfires on some virtualized CPUs (notably Docker Desktop on Apple Silicon), and
  `cryptography` SIGILLs the moment it touches secrets/auth. The stack ships `OPENSSL_armcap=0` (the
  software path — correct, and fast enough for our light crypto) to avoid it; if you overrode
  `OPENSSL_ARMCAP`, unset it. A no-op on x86 hosts.
- **`runtime-worker` shows `Restarting`**: it is still a Stage-0 stub ("no runtime wired yet") that
  wires and exits cleanly, so `restart: unless-stopped` re-runs it — see the wiring follow-up below.
  It is the only such stub; the gateway, ingest-worker, and maintainer-worker run real loops.

## Gateway backend

The gateway runs the **Postgres** backend in the stack (`METIS_GATEWAY_BACKEND=postgres`): ingest
persists raw/normalized/parsed/claims to Postgres + MinIO, consolidates into an indexed memory cell,
and answers (with citations) through the Stage 8 query engine — so data survives a restart. Run it
locally without infra by leaving `METIS_GATEWAY_BACKEND=memory` (the default), an in-process engine
that resets on restart.

**Local models (optional).** Set `METIS_GATEWAY_MODEL_ENDPOINT` (e.g. `http://localhost:11434` for a
host Ollama) to answer with a local LLM (`METIS_GATEWAY_CHAT_MODEL`, default `gemma4:e4b`) and, on
the Postgres backend, retrieve with local embeddings (`METIS_GATEWAY_EMBEDDING_MODEL`, default
`bge-m3`). Both are non-external, so restricted data stays on the node; answer generation falls back
to extractive if the model is unreachable. Unset = deterministic extractive answers + stub vectors.
The `local` profile wires this to the `model-runtime` service — pull the models into it first
(`docker compose exec model-runtime ollama pull bge-m3 && ollama pull gemma4:e4b`).

**Skills / web search.** Point `METIS_GATEWAY_SKILLS_ROOT` at a skills directory (e.g. `skills/`,
which ships `web_search`) to register skills; run one via `POST /skills/run` (operator scope).

## Telegram ingestion (opt-in)

Two transports behind one connector seam (per-chat source config, cursoring, and erasure are
identical for both): the **Business connected-bot** (the default — forward sync of owner-authorized
chats, no account-ban risk) and the opt-in **TDLib** personal-account path (history backfill +
followed channels the bot cannot reach). Both are off unless you bring up the overlay:

```bash
# .env must set METIS_CRED_STORE_KEY (a Fernet key), TELEGRAM_BOT_TOKEN, and — for TDLib —
# TELEGRAM_API_ID / TELEGRAM_API_HASH (from https://my.telegram.org). Generate the Fernet key:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose -f docker-compose.yml -f compose/profiles.local.yml -f compose/profiles.telegram.yml up -d
```

`METIS_CRED_STORE_KEY` **must be the same value** for the gateway and both workers — secrets (OAuth
tokens, TDLib database keys) are encrypted with it and shared through the durable `connector_secrets`
table, so a mismatched key means the worker cannot decrypt what the gateway wrote.

**Bot path (default).** Connect the deployment bot to each owner's account in Telegram's Business
settings and authorize the specific chats; the `telegram-bot-worker` (`MODE=telegram`) drains
`getUpdates` once per cycle and fans the batch out to every active Telegram source. Discover the
chats it has seen with `GET /telegram/chats` (operator), then turn one into a source with
`POST /sources` (`connector: telegram`, `config: {business_connection_id, chat_id, chat_type}`).
Revoking the bot in Telegram pauses its sources automatically (a `business_connection` disable →
`active=false`).

**TDLib path (opt-in, per user).** The `tdlib-lib` one-shot builds `libtdjson` and publishes it into
the `tdliblib` volume; the gateway and `telegram-tdlib-worker` mount it plus the shared `tdlibdata`
volume (the per-account databases). Each user logs in their own account through the gateway:

```bash
# QR (default): returns {"state":"wait_qr","qr_link":"tg://login?token=..."} — render the link as a
# QR code and scan it in Telegram (Settings → Devices → Link Desktop Device).
curl -X POST .../telegram/tdlib/connect -H "Authorization: Bearer <user-id>" -d '{"use_qr":true}'
curl .../telegram/tdlib/connect -H "Authorization: Bearer <user-id>"          # poll until "ready"
# Phone instead of QR: POST {"phone":"+1..."} then POST /telegram/tdlib/connect/code {"code":"..."}
# and, if 2FA is on, POST /telegram/tdlib/connect/password {"password":"..."}.
```

Only the TDLib database-encryption key is stored (encrypted); login codes and the 2FA password are
never persisted. Once a user is `ready`, register their TDLib sources (`connector: telegram`, config
with `tdlib_user_id` set to that user) and the `telegram-tdlib-worker` backfills each chat's history.

### First-deploy validation (manual — needs a live account)

The credential-free replay suite covers the connector/transport/drain logic; the live login +
backfill can only be checked against a real Telegram account, so validate once per deployment:

1. **libtdjson loads.** After `up`, the `tdlib-lib` service should exit 0 having listed
   `libtdjson.so*`. Confirm the gateway can load it:
   `docker compose exec gateway python -c "from metis_ingestion.connectors import load_tdjson_library; load_tdjson_library('/opt/tdlib/libtdjson.so'); print('ok')"`.
   A failure here is almost always an OpenSSL/zlib ABI mismatch — rebuild `tdlib.Dockerfile` on the
   same base as the app image (it already pins `python:3.12-slim`), and bump `TDLIB_REF` if the build
   itself fails. The C++ build is slow (many minutes) and is **not** exercised by CI.
2. **Login.** Run the QR (or phone/2FA) flow above and confirm `state` reaches `ready`; check
   `connector_secrets` holds a `telegram_tdlib:db_key:<user>` row (ciphertext only).
3. **Backfill.** Register a small TDLib source and confirm artifacts appear (`GET /jobs`, the
   evidence browser) and that re-running the worker does not re-ingest (the per-chat cursor dedups).
4. **Shared state.** The gateway writes the database under `tdlibdata`; the worker must reopen the
   **same** volume — if backfill logs "did not authorize", confirm both mount `tdlibdata` and share
   `METIS_CRED_STORE_KEY`.

Poll conservatively (TDLib flood-waits surface as retryable rate-limit errors); the bot path needs
no Premium and carries no ban risk, so prefer it and reserve TDLib for backfill/followed-channels.

## Known wiring follow-up

The `ingest-worker` (queue + the Telegram drains) and the `maintainer-worker` (its scheduled
job-kind poll loop) run real long-running loops; the gateway is a fully serving uvicorn process. Only
the `runtime-worker` still runs its Stage-0 entrypoint (wire-and-exit) — the engine logic lives in
the packages and the core `Worker` lease/handle loop exists, so turning it into a long-running loop is
a code change, not new infrastructure (the Compose stack already defines and wires it). Until then it
exits cleanly and Compose re-runs it (a harmless `Restarting` churn); set `restart: "no"` on that one
service if the churn is noisy.
