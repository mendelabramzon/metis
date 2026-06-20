# Server Deployment Stage 1 Detailed Plan: Ten-User Server Deployment

Parent: [server-deployment-product-roadmap.md](server-deployment-product-roadmap.md), Stage 1.
Builds on the completed engineering stages 0–15 (see [high-level-implementation-plan.md](high-level-implementation-plan.md)).

This stage turns the engine into a multi-user server for ~10 people in one organization:
personal and shared workspaces, production auth, a configurable cloud-first model plane, live
email/document/Telegram ingestion driven by durable jobs, and an evidence-rich context-exoskeleton
UI. It is extension work, not greenfield — most of it wires product surfaces and live transports
onto seams that already exist (the model router, the connector `Transport` interface, durable
source/job state, the Postgres backend, the hybrid memory index). The numbering below mirrors the
roadmap's workstreams 1.1–1.6.

## Implementation Status (2026-06-20)

Most of Stage 1 is built and on `main`; what remains is the bulk of the UI (1.6), per-action
execution dispatch (1.5), and the opt-in Telegram TDLib path (1.4). Status by workstream:

- **1.1 Deployment foundation — DONE.** Caddy TLS proxy, OTel spine + dashboards/alerts, scheduled
  restore drill, resource budgets.
- **1.2 Identity — DONE** (prior): orgs/users/workspaces/memberships, RBAC, the isolation gate.
- **1.3 Provider plane — DONE**, including the embedding-capability manifest (self-hosted TEI) tail.
- **1.4 Live ingestion:**
  - Email/Drive (IMAP, Gmail/Drive over OAuth) + file upload + parser-quality — DONE (prior).
  - **Telegram — DONE for the bot path** (the chosen default): the connector (CHAT_MESSAGE rendering
    + recorded replay), per-chat `SourceConfig.config` + registry validation, the live Business
    connected-bot transport, the dedicated `mode=telegram` worker drain (one global getUpdates offset
    fanned out per chat), deletion→tombstone, and chat discovery (`telegram_chats` table +
    `GET /telegram/chats`).
  - **Telegram — TODO:** the opt-in TDLib transport (history backfill + followed channels) and
    `business_connection` revocation handling. Global offset persistence was deliberately skipped
    (Telegram confirms updates server-side once the offset advances + per-source cursors dedup).
- **1.5 Durable state + command surface:**
  - Durable job/wiki/approval state + erasure/evidence/contradiction/memory surfaces — DONE (prior).
  - **Proposed-action command surface — DONE:** the action vocabulary (`ProposedAction` / `ActionRisk`
    / `ActionKind` / `ActionStatus`), the durable `ActionStore`, the LLM interpreter
    (`INTERPRET_COMMAND` task class + prompt → typed action, structured output, read-only ANSWER
    fallback), and `routers/actions.py` (interpret → propose → risk-gated approve/reject).
  - **TODO:** execution *dispatch* — an approved effectful action actually running against the engines
    (start a sync, apply a memory/wiki patch, …). Today the lifecycle is recorded and only read-only
    ANSWER runs (via the console's run-answer shortcut).
- **1.6 UI — STARTED.** The single-file context-exoskeleton console at `/` (command → proposed-action
  cards with risk badges + a status-filtered inbox, Telegram chat discovery, and sources / jobs /
  approvals / audit / ask). **TODO:** login + workspace switcher, source-setup forms (Telegram bot
  connect, OAuth, upload), contradictions + spend tabs, evidence drill-down — and a real SPA if a
  richer UX is wanted.

**Key decisions (settled — do not relitigate):**

- **Telegram is bot-first (hybrid).** The sanctioned Business connected-bot is the default transport
  (no account-ban risk, no encrypted-session subsystem, reaches private chats); TDLib is opt-in only
  for what the bot cannot do (history backfill, followed channels). Both behind the same `Transport`
  seam, so per-chat `SourceConfig`/cursoring/erasure are identical.
- **Telegram delivery is polling** (`getUpdates`), drained once per cycle by the dedicated worker mode
  and fanned out to every active chat source — not per-source jobs (one queue per bot token).
- **The command interpreter is LLM-based**, via the model plane's structured-output path.

**Suggested next steps (in order):** 1.6 source-setup forms + workspace switcher → 1.6
contradictions/spend tabs → 1.5 execution dispatch (map each approved `ActionKind` to its engine,
gated by risk) → 1.4 Telegram TDLib opt-in.

## Objective

- Replace dev-token auth with organization / user / workspace / membership identity and RBAC,
  enforced above the existing `workspace_id` storage filter.
- Promote the existing `MetisModelRouter` into a configurable provider registry (cloud, local,
  and self-hosted HF) with per-workspace policy, capability manifests, and per-task-class spend.
- Write live connector transports (IMAP, Gmail/Drive over OAuth, and Telegram) behind the existing
  connector spine, with attachment/media handling, durable cursors/runs, and replay fixtures.
  Telegram defaults to a sanctioned Business connected-bot ("secretary mode") for forward sync of
  owner-authorized chats; an opt-in TDLib personal-account path adds history backfill and followed
  channels where required.
- Replace the in-memory job queue with a durable queue and turn the ingest/runtime worker stubs
  into real lease-and-dispatch loops.
- Make job, proposed-action, approval, and wiki state durable in both gateway backends.
- Ship a real context-exoskeleton UI: workspace switcher, source dashboard, evidence browser,
  command/chat entry, contextual answer cards with citations, proposed-action cards with
  confirmation, contradiction/approval inboxes, and erasure.

Non-goals (deferred to Stage 2/3): new official connectors beyond email/Drive/Telegram,
browser-driven skills, outbound connector actions such as sending Telegram/email messages,
the deep-research workflow, signed cross-company exchange. GPU serving is optional here.

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
  identity, source config, proposed actions, and provider config are not gateway-local dicts.
- **Citation + truth hierarchy.** Live connectors and the upload path still emit
  `RawArtifact`/`NormalizedDoc` and flow through the unchanged Stage 3 pipeline; no surface writes
  memory directly.
- **Human agency over side effects.** Natural-language UI may interpret intent and propose typed
  actions, but write/side-effectful actions execute only through explicit approval, with visible
  consequences and audit records.

## Package Ownership

- `metis-protocol`: new identity, source-config, model-capability, and proposed-action schemas.
- `metis-core`: identity/provider stores + migrations, provider registry, spend accounting,
  durable job/action/approval/wiki stores, capability-aware router config.
- `metis-ingestion` (+ `services/ingest-worker`): live transports, OAuth connectors, attachment
  extraction, Telegram account/chat ingestion, parser-quality path, the worker dispatch loop.
- `services/gateway`: auth/RBAC, request-scoped workspace resolution, provider/spend/source/upload
  routers, Telegram account connection, durable wiki/approval/action inboxes, the UI app.
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
  sources.py            # SourceConfig (+ typed config payload), SourceCredentialRef,
                        # SourceCursor, ConnectorRun
  actions.py            # ProposedAction, ActionRisk, ApprovalDecision
packages/metis-core/src/metis_core/
  stores/identity_store.py      # CRUD + membership resolution (workspace_id already on every row)
  stores/source_store.py        # source configs, cursors, connector runs
  migrations/versions/0003_identity_sources_actions.py
services/gateway/src/metis_gateway/
  auth.py               # (rewrite) sessions/tokens → user; RBAC by Role
  deps.py               # (extend) request-scoped workspace resolution + membership gate
  middleware.py         # principal extraction, audit-actor binding
  routers/workspaces.py # workspace CRUD + membership
  routers/users.py      # user/session
```

**Schemas/interfaces:** `Workspace` already exists in the substrate; add `Organization`, `User`,
`WorkspaceMembership`, `Role` (owner/admin/member/viewer/auditor), `WorkspaceKind`
(personal/shared/external-later). Extend `SourceConfig` with a connector-specific config payload
validated by the registry: email mailbox/labels, Drive folder/shared-drive selection, and Telegram
account/chat/channel selection. Add `ProposedAction`/`ActionRisk` so the UI can persist "the LLM
understood this request as this concrete action" before any effectful execution. Audit events
(existing `AuditEvent`) gain a real actor identity.

**Steps:**

1. Add identity schemas to `metis-protocol`; add stores + migration `0003` to `metis-core`.
2. Rewrite gateway `auth.py`: real sessions/tokens resolving to a `User`; RBAC by `Role`.
3. Extend `deps.py` so each request resolves an active workspace and asserts caller membership
   *before* any retrieval; bind the real actor onto emitted audit events.
4. Auto-provision a personal workspace per user; make shared workspaces explicit (no
   organization-wide implicit sharing).
5. Map source ACL → sensitivity as a floor (unknown/private ⇒ more restrictive). Telegram private
   chats and private groups default to `CONFIDENTIAL`; sensitive personal chats may be upgraded to
   `RESTRICTED` by the user or policy.
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

## Workstream 1.4 — Live Ingestion for Email, Documents, and Telegram

**Files:**

```text
packages/metis-ingestion/src/metis_ingestion/connectors/
  transports/imap_transport.py   # live Transport over imaplib (LOGIN/SELECT/SEARCH/FETCH → bytes)
  transports/http_transport.py   # live Transport for HTTP/API connectors
  transports/telegram_bot_transport.py   # default: Business connected-bot updates (forward sync) + replay
  transports/telegram_tdlib_transport.py # opt-in: TDLib adapter for backfill + followed channels + replay
  oauth.py                       # OAuth flows + token refresh (secrets via Stage 14 cred store)
  gmail.py                       # Google API email connector (labels, shared mailboxes)
  gdrive.py                      # Drive: shared drives, folder selection, Docs/Sheets export
  imap.py                        # (extend) attachment extraction; currently text/plain body only
  telegram.py                    # selected chats/groups/channels → chat_message docs (bot default, TDLib opt-in)
  telegram_session.py            # opt-in TDLib account sessions; encrypted; QR/phone/code/2FA states
packages/metis-ingestion/src/metis_ingestion/parsers/
  layout_pdf.py                  # layout-aware path for complex PDFs (tables, columns)
  ocr.py                         # OCR/VLM fallback when deterministic coverage is low
  quality.py                     # parse-quality report (coverage, tables, pages, warnings)
services/ingest-worker/src/metis_ingest_worker/
  app.py                         # (rewrite) lease + dispatch durable connector/file jobs
services/gateway/src/metis_gateway/routers/
  upload.py                      # file upload (batch, progress, parse status, retry)
  oauth.py                       # OAuth callback endpoints
  telegram.py                    # bot connect + authorized-chat selection (default); TDLib account connect (opt-in)
```

**Steps:**

1. Implement `ImapTransport` (and a shared `http_transport`) behind the existing `Transport`
   protocol; the connector spine (cursors, rate limiting, retry/backoff, thread reconstruction)
   stays unchanged.
2. Add attachment extraction to `imap.py` (parse non-text parts through the parser registry).
3. Implement `gmail.py` and `gdrive.py` over OAuth (`oauth.py` + the encrypted cred store); persist
   `SourceCursor`/`ConnectorRun` rows.
4. Implement the **default Telegram transport** as a Business connected-bot ("secretary mode"): the
   account owner connects the deployment bot and authorizes specific chats; the bot then receives
   normal Bot API updates for those chats (including private DMs), excluding bot/self messages. Each
   authorized private chat, group, or supergroup becomes its own `SourceConfig` so sensitivity,
   cursoring, and erasure stay per conversation. No Premium subscription and no encrypted account
   session are required; the bot token is a deployment secret and the per-user link is just a
   `business_connection_id` + authorized chat ids.
5. Add Telegram bot setup: connect the bot to a user's account, let the owner authorize chats in
   Telegram's own (revocable) UI, enumerate the authorized chats, take explicit user selection, and
   set per-chat default sensitivity. Persist only the business-connection id and source config;
   never store login codes or 2FA secrets.
6. Add forward incremental sync over the bot: process `business_message` / `edited_business_message`
   / `deleted_business_messages` updates (webhook or polled `getUpdates`), persist an opaque cursor
   such as `{chat_id,last_message_id,last_date}`, and reconcile on schedule. Edits create a new
   artifact version; deletions tombstone the raw artifact and derived claims.
7. Add the **opt-in TDLib personal-account transport** behind the same `Transport` seam, enabled
   explicitly per user, for the two things the bot cannot do: history backfill (page message history
   for selected sources) and followed channels the user does not administer. It carries QR/phone/2FA
   authorization state and an encrypted local session/database; store only encrypted session keys —
   never login codes or 2FA secrets — poll conservatively, and handle flood waits and revocation.
8. Render Telegram messages (from either transport) as canonical JSON raw artifacts plus readable
   markdown `NormalizedDoc`s with `ArtifactKind.CHAT_MESSAGE`; include sender, timestamp, reply/thread
   context, forward/edit/delete metadata, and attachment/media references. Download media only when
   selected and within budgets; otherwise preserve metadata and a source locator.
9. Replace `InMemoryJobQueue` usage with the durable queue (1.5) and rewrite the ingest worker into
   a real lease/execute loop; keep the inline POST path for single-doc upload.
10. Add the file-upload API/UI path for PDF/DOCX/XLSX/CSV/TXT/MD/HTML/EML with visible parse status.
11. Add the layout-aware + OCR parser paths and the parse-quality report; keep
   `raw → parsed → segment → claim → memory` intact (parsers never write memory).

## Workstream 1.5 — Context Exoskeleton Product Surface + Durable State

**Files:**

```text
packages/metis-core/src/metis_core/
  stores/job_store.py        # durable job queue (replaces InMemoryJobQueue for the server)
  stores/action_store.py     # durable proposed actions + approval decisions
  stores/approval_store.py   # durable approval inbox (memory/wiki/action approvals)
  stores/wiki_inbox_store.py # durable wiki patch inbox
services/gateway/src/metis_gateway/
  backend.py                 # (extend) wire durable job/action/approval/wiki stores into backends
  routers/{actions,contradictions,memory_review,wiki,erasure}.py
```

**Steps:**

1. Make the job queue, proposed-action/approval inbox, and wiki inbox durable; `build_backend` and
   `build_postgres_backend` both stop using in-memory versions for server deployment.
2. Add a command/chat surface that turns free-text requests into typed intent: answer a question,
   find evidence, inspect a source, draft a response, create a memory/wiki patch, start a sync, or
   propose a connector/source change. The UI must display the interpreted action before execution
   when the request is ambiguous or effectful.
3. Implement proposed-action cards with risk tiers:
   read-only answers run without confirmation; internal reversible changes require undo or inbox
   approval; memory/wiki changes show a diff; external side effects are approval-only and stay out
   of Stage 1 unless implemented as a later skill. Every card shows inputs used, expected effect,
   sensitivity, and audit target.
4. Expose the product surfaces over durable state: source dashboard (email, Drive, upload,
   Telegram accounts and selected chats/channels), evidence browser
   (`raw → spans → claims → mem cells → wiki`), contradiction inbox, memory review
   (accept/retract/mark-stale), wiki projection, erasure (propagate tombstones to derived
   artifacts).
5. Treat memory as a write/manage/read loop in the UI: review and supersession are first-class,
   not hidden behind a vector store.
6. Keep execution/task state separate from semantic memory (groundwork for Stage 2 research).

## Workstream 1.6 — API and UI Deliverables

**Files:** consolidate the routers above under `services/gateway/src/metis_gateway/routers/`;
replace the 94-line `web/index.html` debug console with a real frontend app (`services/gateway/web/`
or a separate SPA served behind the proxy).

**API:** user/session; workspace CRUD + membership; source config + OAuth callback; Telegram
account connection + chat/channel selection; file upload + connector sync; query/command/chat with
workspace selection + citations; proposed-action inspect/approve/reject; job inspect/retry/cancel;
audit; provider config + spend (operators).

**UI:** login + workspace switcher; source setup (email/Drive/upload/Telegram selected chats and
channels); quiet context panel; command/chat with citations + evidence drilldown; proposed-action
cards with confirmation; jobs/errors dashboard; approval + contradiction inbox; provider/spend
dashboard.

## Tests And Fixtures

- **Workspace isolation (the gate):** negative test that cross-user personal retrieval is
  impossible through every store and the gateway; membership checked before retrieval.
- **RBAC:** each `Role` reaches exactly its allowed routes; auditor is read-only.
- **Provider routing:** restricted data never routes external; cloud-primary/local-fallback order
  honored; capability manifest required before enable; spend caps enforced.
- **Live transports (recorded):** `ImapTransport`/Gmail/Drive run against recorded fixtures with no
  live credentials (extend the existing replay suite); cursor replay deterministic; attachments
  extracted.
- **Telegram connector replay (both transports):** recorded fixtures with no live credentials —
  bot path: business-connection authorization, forward `business_message`/edit/delete updates,
  cursor replay, media metadata; opt-in TDLib path: chat/channel enumeration and selected-chat
  backfill cursor replay; plus per-chat source erasure for both.
- **Durable job/approval/wiki:** survive a gateway restart; ingest worker leases and completes a
  queued job; a held approval resumes after restart.
- **Action proposals:** natural-language commands produce typed proposed actions; read-only actions
  do not require confirmation; memory/wiki changes show diffs; external side effects are blocked or
  held for explicit approval.
- **UI source flows:** source setup selects email mailboxes/labels, Drive folders, upload batches,
  and Telegram chats/channels without exposing credentials or unselected conversation content.
- **Parser quality:** complex-PDF and scanned-PDF fixtures produce coverage/table/OCR reports;
  low-coverage triggers OCR fallback.
- **Upload flow:** every supported format ingests with visible parse status.
- **Backup/restore:** the restore drill round-trips a fixture workspace.

## Acceptance Criteria

Traces to the roadmap's Stage 1 acceptance list:

- 10 users log in; each has a personal workspace; users can join a shared workspace.
- A shared Drive folder, a personal email source, and selected Telegram chats/channels ingest
  end-to-end via *queued* connector jobs.
- PDF/DOCX/XLSX/CSV/TXT/MD/HTML/EML ingest with visible parse status.
- Queries target personal/shared/mixed context and cite source-backed evidence.
- The UI can interpret a free-text request into a visible proposed action, show the evidence or
  source scope it will use, and require approval before any memory/wiki write or external side
  effect.
- A user cannot retrieve another user's personal context (enforced and tested).
- Cloud LLM + embedding providers are configurable without code edits.
- An HF model behind TGI/vLLM/TEI registers via its capability manifest.
- Backups restore a fixture deployment; spend and connector failures are visible to operators.

## Risks And Open Questions

- **ACL leakage is existential.** Identity must layer on the storage filter; the negative isolation
  test is the gate, not a nicety.
- **OAuth/token lifecycle** (refresh, expiry, revocation) will cost more than parser work;
  centralize in `oauth.py` + the encrypted cred store.
- **Telegram transport choice.** Default to the sanctioned Business connected-bot: it reaches
  owner-authorized chats (including private DMs) for forward sync with no account-ban risk and no
  encrypted-session subsystem, but cannot backfill pre-connection history or read followed channels.
  The opt-in TDLib path covers exactly those two gaps at the cost of QR/phone/2FA sessions, local
  encrypted state, flood waits, and userbot risk — enable it per user, conservatively polled, never
  as the default. Both sit behind the same `Transport` seam, so per-chat `SourceConfig`, cursoring,
  and erasure are identical. Store only the business-connection id (bot) or encrypted session keys
  (TDLib); never login codes or 2FA secrets.
- **In-memory → durable migration** of job/approval/wiki state touches both backends; sequence it
  before live ingestion so nothing important lives only in memory on a server.
- **Embedding-dimension lock-in:** switching the production embedding model is a re-index by design
  (version-gating); make that an explicit operator action, not a silent config flip.
- **Spend blowups:** caps must be enforced at the router, not just reported.
- **OCR/VLM cost and latency:** gate strictly on low deterministic coverage.
- **Approval fatigue and overreliance:** a chat-like UI can feel authoritative even when retrieval
  is wrong. Keep the interface calm: cite evidence, expose uncertainty, make dismissal/correction
  cheap, and reserve blocking confirmations for meaningful risk boundaries.

## Sequencing

Follow roadmap Milestones A→C: 1.2 identity → 1.5 durable state + 1.3 provider plane → 1.4 file
upload then live ingestion + worker loops (email/Drive first, then the Telegram bot connector; the
opt-in TDLib backfill path lands after per-chat erasure is in place) → 1.6 UI → 1.4 parser-quality
upgrades. Identity is the hard gate;
live connectors do not turn on until isolation tests are green.
