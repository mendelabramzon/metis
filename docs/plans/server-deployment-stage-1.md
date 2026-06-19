# Server Deployment Stage 1 Detailed Plan: Ten-User Server Deployment

Parent: [server-deployment-product-roadmap.md](server-deployment-product-roadmap.md), Stage 1.
Builds on the completed engineering stages 0–15 (see [high-level-implementation-plan.md](high-level-implementation-plan.md)).

This stage turns the engine into a multi-user server for ~10 people in one organization:
personal and shared workspaces, production auth, a configurable cloud-first model plane, live
email/document ingestion driven by durable jobs, and an evidence-rich product UI. It is
extension work, not greenfield — most of it wires product surfaces and live transports onto
seams that already exist (the model router, the connector `Transport` interface, the durable
Postgres backend, the hybrid memory index). The numbering below mirrors the roadmap's
workstreams 1.1–1.6.

## Objective

- Replace dev-token auth with organization / user / workspace / membership identity and RBAC,
  enforced above the existing `workspace_id` storage filter.
- Promote the existing `MetisModelRouter` into a configurable provider registry (cloud, local,
  and self-hosted HF) with per-workspace policy, capability manifests, and per-task-class spend.
- Write live connector transports (IMAP, Gmail/Drive over OAuth) behind the existing
  `Transport` seam, with attachment extraction and durable cursors/runs.
- Replace the in-memory job queue with a durable queue and turn the ingest/runtime worker stubs
  into real lease-and-dispatch loops.
- Make job, wiki, and approval state durable in both gateway backends.
- Ship a real product UI (workspace switcher, source dashboard, evidence browser, chat with
  citations, contradiction/approval inboxes, erasure).

Non-goals (deferred to Stage 2/3): new official connectors beyond email/Drive, browser-driven
skills, the deep-research workflow, signed cross-company exchange. GPU serving is optional here.

## Invariants Preserved

This stage must not weaken any [engineering invariant](server-deployment-product-roadmap.md#engineering-invariants-we-keep).
The load-bearing ones for Stage 1:

- **Membership is layered *on top of* the storage filter, never around it.** Every store query
  already filters by `workspace_id`; identity adds a membership check *before* retrieval, and a
  negative isolation test proves there is no path that skips it.
- **Policy outside prompts.** Provider selection stays in `MetisModelRouter`, which enforces the
  external-provider allowlist before any prompt is built. The config surface feeds the router; it
  does not add per-call branching that could bypass it.
- **New product concepts enter as `metis-protocol` schemas + `metis-core` stores + migrations** —
  identity and provider config are not gateway-local dicts.
- **Citation + truth hierarchy.** Live connectors and the upload path still emit
  `RawArtifact`/`NormalizedDoc` and flow through the unchanged Stage 3 pipeline; no surface writes
  memory directly.

## Package Ownership

- `metis-protocol`: new identity, source-config, and model-capability schemas.
- `metis-core`: identity/provider stores + migrations, provider registry, spend accounting,
  durable job queue, capability-aware router config.
- `metis-ingestion` (+ `services/ingest-worker`): live transports, OAuth connectors, attachment
  extraction, parser-quality path, the worker dispatch loop.
- `services/gateway`: auth/RBAC, request-scoped workspace resolution, provider/spend/source/upload
  routers, durable wiki/approval inboxes, the UI app.
- `deploy`: TLS/routing, backups/restore drills, OTel dashboards, resource budgets.

## Workstream 1.1 — Production Deployment Foundation

**Files (extend `deploy/`):**

```text
deploy/compose/
  proxy.yml             # TLS termination + domain routing (Caddy/Traefik) in front of the gateway
  budgets.env           # hard caps: doc size, job runtime, spend/workspace/day, skill runtime
deploy/observability/
  dashboards/           # failed jobs, ingestion lag, model spend, policy denials, parser fails
  alerts.yml            # spend ceiling, job-failure rate, ingestion-lag, restore-drill freshness
deploy/backup/
  restore_drill.py      # scheduled restore into a scratch stack + fixture-workspace assertion
deploy/src/metis_deploy/
  budgets.py            # typed budget config consumed by gateway/workers
```

**Steps:**

1. Put a TLS-terminating reverse proxy in front of the gateway; route one domain to the stack.
2. Ensure Postgres ships the `pgvector` extension (already required by the memory index — make it
   a deploy precondition, not a runtime surprise) and a single migration init step (no per-service
   races); reuse `deploy/migrate/`.
3. Wire OTel traces across gateway → workers → stores; surface the operator dashboards from the
   roadmap (failed jobs, ingestion lag, spend, policy denials, parser failures, rate limits).
4. Enforce hard resource budgets (`budgets.py`) at the gateway and worker entry points.
5. Convert `deploy/backup/` into a scheduled backup + an automated restore drill that asserts a
   fixture workspace round-trips.

## Workstream 1.2 — Identity, Workspaces, and ACLs (the first hard gate)

**Files:**

```text
packages/metis-protocol/src/metis_protocol/
  identity.py           # Organization, User, WorkspaceMembership, Role, WorkspaceKind
  sources.py            # SourceConfig, SourceCredentialRef, SourceCursor, ConnectorRun
packages/metis-core/src/metis_core/
  stores/identity_store.py      # CRUD + membership resolution (workspace_id already on every row)
  stores/source_store.py        # source configs, cursors, connector runs
  migrations/versions/0003_identity_and_sources.py
services/gateway/src/metis_gateway/
  auth.py               # (rewrite) sessions/tokens → user; RBAC by Role
  deps.py               # (extend) request-scoped workspace resolution + membership gate
  middleware.py         # principal extraction, audit-actor binding
  routers/workspaces.py # workspace CRUD + membership
  routers/users.py      # user/session
```

**Schemas/interfaces:** `Workspace` already exists in the substrate; add `Organization`, `User`,
`WorkspaceMembership`, `Role` (owner/admin/member/viewer/auditor), `WorkspaceKind`
(personal/shared/external-later). Audit events (existing `AuditEvent`) gain a real actor identity.

**Steps:**

1. Add identity schemas to `metis-protocol`; add stores + migration `0003` to `metis-core`.
2. Rewrite gateway `auth.py`: real sessions/tokens resolving to a `User`; RBAC by `Role`.
3. Extend `deps.py` so each request resolves an active workspace and asserts caller membership
   *before* any retrieval; bind the real actor onto emitted audit events.
4. Auto-provision a personal workspace per user; make shared workspaces explicit (no
   organization-wide implicit sharing).
5. Map source ACL → sensitivity as a floor (unknown/private ⇒ more restrictive).
6. **Gate:** live connectors (1.4) stay disabled until the isolation suite passes, including a
   negative test that user A cannot retrieve user B's personal context through any router/store.

## Workstream 1.3 — Model and Embedding Provider Plane

**Files:**

```text
packages/metis-protocol/src/metis_protocol/
  model_capability.py   # ModelCapability: chat/embed, ctx window, tool/JSON support+reliability,
                        # embedding dim, vision/OCR, tokenizer, cost, latency, privacy tier
packages/metis-core/src/metis_core/llm/
  registry.py           # ModelProviderConfig → assembled provider list (ordered, with fallback)
  spend.py              # per-task-class spend accounting + budget enforcement (extends budget.py)
  routing_config.py     # (extend) capability-driven tier/role selection
services/gateway/src/metis_gateway/
  models.py             # (rewrite) build_model_caller: assemble MetisModelRouter from config
  settings.py           # (extend) provider/key fields OR delegate to ModelProviderConfig store
  routers/providers.py  # operator CRUD for ModelProviderConfig + capability manifests
  routers/spend.py      # per-workspace / per-task-class spend read API
```

**Steps:**

1. Add `ModelCapability` to `metis-protocol` and a `ModelProviderConfig` store to `metis-core`.
2. Build `registry.py` that turns configured providers into an ordered provider list for
   `MetisModelRouter` (cloud-primary + local fallback) — reusing the *existing* `AnthropicProvider`
   and `OpenAICompatProvider`; no new adapters.
3. Replace the single-Ollama `build_model_caller` in gateway `models.py` with a config-driven
   assembly; keep `build_embedding_router` but source the embedding endpoint (OpenAI / HF TEI /
   Ollama) from config.
4. Add `WorkspaceModelPolicy` (whether external providers may see a source's content) and feed it
   to the router's pre-prompt allowlist.
5. Add per-task-class spend accounting (`spend.py`) and expose it to operators; enforce
   per-workspace daily caps.
6. Require a capability manifest before a model is enabled; for self-hosted HF, the manifest maps a
   TGI/vLLM/TEI endpoint to an OpenAI-compatible URL the existing provider consumes.

**Anti-goals:** per-model-repo adapters; name-based auto-selection; fine-tuning on private data.

## Workstream 1.4 — Live Ingestion for Email and Documents

**Files:**

```text
packages/metis-ingestion/src/metis_ingestion/connectors/
  transports/imap_transport.py   # live Transport over imaplib (LOGIN/SELECT/SEARCH/FETCH → bytes)
  transports/http_transport.py   # live Transport for HTTP/API connectors
  oauth.py                       # OAuth flows + token refresh (secrets via Stage 14 cred store)
  gmail.py                       # Google API email connector (labels, shared mailboxes)
  gdrive.py                      # Drive: shared drives, folder selection, Docs/Sheets export
  imap.py                        # (extend) attachment extraction; currently text/plain body only
packages/metis-ingestion/src/metis_ingestion/parsers/
  layout_pdf.py                  # layout-aware path for complex PDFs (tables, columns)
  ocr.py                         # OCR/VLM fallback when deterministic coverage is low
  quality.py                     # parse-quality report (coverage, tables, pages, warnings)
services/ingest-worker/src/metis_ingest_worker/
  app.py                         # (rewrite) lease + dispatch durable connector/file jobs
services/gateway/src/metis_gateway/routers/
  upload.py                      # file upload (batch, progress, parse status, retry)
  oauth.py                       # OAuth callback endpoints
```

**Steps:**

1. Implement `ImapTransport` (and a shared `http_transport`) behind the existing `Transport`
   protocol; the connector spine (cursors, rate limiting, retry/backoff, thread reconstruction)
   stays unchanged.
2. Add attachment extraction to `imap.py` (parse non-text parts through the parser registry).
3. Implement `gmail.py` and `gdrive.py` over OAuth (`oauth.py` + the encrypted cred store); persist
   `SourceCursor`/`ConnectorRun` rows.
4. Replace `InMemoryJobQueue` usage with the durable queue (1.5) and rewrite the ingest worker into
   a real lease/execute loop; keep the inline POST path for single-doc upload.
5. Add the file-upload API/UI path for PDF/DOCX/XLSX/CSV/TXT/MD/HTML/EML with visible parse status.
6. Add the layout-aware + OCR parser paths and the parse-quality report; keep
   `raw → parsed → segment → claim → memory` intact (parsers never write memory).

## Workstream 1.5 — Context Exoskeleton Product Surface + Durable State

**Files:**

```text
packages/metis-core/src/metis_core/
  stores/job_store.py        # durable job queue (replaces InMemoryJobQueue for the server)
  stores/approval_store.py   # durable approval inbox
  stores/wiki_inbox_store.py # durable wiki patch inbox
services/gateway/src/metis_gateway/
  backend.py                 # (extend) wire durable job/approval/wiki stores into both backends
  routers/{contradictions,memory_review,wiki,erasure}.py
```

**Steps:**

1. Make the job queue, approval inbox, and wiki inbox durable; `build_backend` and
   `build_postgres_backend` both stop using in-memory versions for server deployment.
2. Expose the product surfaces over the durable state: source dashboard, evidence browser
   (`raw → spans → claims → mem cells → wiki`), contradiction inbox, memory review
   (accept/retract/mark-stale), wiki projection, erasure (propagate tombstones to derived
   artifacts).
3. Treat memory as a write/manage/read loop in the UI: review and supersession are first-class,
   not hidden behind a vector store.
4. Keep execution/task state separate from semantic memory (groundwork for Stage 2 research).

## Workstream 1.6 — API and UI Deliverables

**Files:** consolidate the routers above under `services/gateway/src/metis_gateway/routers/`;
replace the 94-line `web/index.html` debug console with a real frontend app (`services/gateway/web/`
or a separate SPA served behind the proxy).

**API:** user/session; workspace CRUD + membership; source config + OAuth callback; file upload +
connector sync; query/chat with workspace selection + citations; job inspect/retry/cancel; audit;
provider config + spend (operators).

**UI:** login + workspace switcher; source setup (email/Drive/upload); chat with citations +
evidence drilldown; jobs/errors dashboard; approval + contradiction inbox; provider/spend dashboard.

## Tests And Fixtures

- **Workspace isolation (the gate):** negative test that cross-user personal retrieval is
  impossible through every store and the gateway; membership checked before retrieval.
- **RBAC:** each `Role` reaches exactly its allowed routes; auditor is read-only.
- **Provider routing:** restricted data never routes external; cloud-primary/local-fallback order
  honored; capability manifest required before enable; spend caps enforced.
- **Live transports (recorded):** `ImapTransport`/Gmail/Drive run against recorded fixtures with no
  live credentials (extend the existing replay suite); cursor replay deterministic; attachments
  extracted.
- **Durable job/approval/wiki:** survive a gateway restart; ingest worker leases and completes a
  queued job; a held approval resumes after restart.
- **Parser quality:** complex-PDF and scanned-PDF fixtures produce coverage/table/OCR reports;
  low-coverage triggers OCR fallback.
- **Upload flow:** every supported format ingests with visible parse status.
- **Backup/restore:** the restore drill round-trips a fixture workspace.

## Acceptance Criteria

Traces to the roadmap's Stage 1 acceptance list:

- 10 users log in; each has a personal workspace; users can join a shared workspace.
- A shared Drive folder and a personal email source ingest end-to-end via a *queued* connector job.
- PDF/DOCX/XLSX/CSV/TXT/MD/HTML/EML ingest with visible parse status.
- Queries target personal/shared/mixed context and cite source-backed evidence.
- A user cannot retrieve another user's personal context (enforced and tested).
- Cloud LLM + embedding providers are configurable without code edits.
- An HF model behind TGI/vLLM/TEI registers via its capability manifest.
- Backups restore a fixture deployment; spend and connector failures are visible to operators.

## Risks And Open Questions

- **ACL leakage is existential.** Identity must layer on the storage filter; the negative isolation
  test is the gate, not a nicety.
- **OAuth/token lifecycle** (refresh, expiry, revocation) will cost more than parser work;
  centralize in `oauth.py` + the encrypted cred store.
- **In-memory → durable migration** of job/approval/wiki state touches both backends; sequence it
  before live ingestion so nothing important lives only in memory on a server.
- **Embedding-dimension lock-in:** switching the production embedding model is a re-index by design
  (version-gating); make that an explicit operator action, not a silent config flip.
- **Spend blowups:** caps must be enforced at the router, not just reported.
- **OCR/VLM cost and latency:** gate strictly on low deterministic coverage.

## Sequencing

Follow roadmap Milestones A→C: 1.2 identity → 1.5 durable state + 1.3 provider plane → 1.4 file
upload then live ingestion + worker loops → 1.6 UI → 1.4 parser-quality upgrades. Identity is the
hard gate; live connectors do not turn on until isolation tests are green.
