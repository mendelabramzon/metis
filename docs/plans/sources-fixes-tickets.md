# Sources & Providers Fixes — Tickets

Three issues reported against the running deployment, grounded in a read of the current tree
(`services/gateway`, `packages/metis-core`, `apps/web`). Two of the three are **already
implemented in the codebase but disabled/invisible** in a deployment that hasn't been configured —
the work is to make that state visible and operator-configurable, not to build the capability from
scratch.

**Legend.** Layer: `GW` gateway/backend, `CORE` packages, `FE` frontend. Size: `S` ≤1 day,
`M` 1–3 days, `L` 3–5 days. Each ticket preserves the engine invariants (no direct memory writes;
policy stays in the router; append-only/tombstone erasure; embedding version-gating).

---

## Diagnosis (what's actually true)

- **I1 — no way to delete an uploaded source.** *Genuinely missing.* `POST /workspaces/{ws}/upload`
  ingests files tagged with the `upload` connector but **never registers a `SourceConfig`**, so
  uploads never appear in the Sources list and the source-erasure path (`DELETE /sources/{id}`)
  cannot reach them. The per-artifact erasure primitive (`erase_artifact` → tombstone cascade +
  blob delete, workspace-isolated) already exists; there is just no list/delete surface for
  uploaded documents.
- **I2 — "asking goes without an LLM."** *Config + invisibility, not missing capability.* Parsing is
  deterministic by design (an invariant — parsers never call a model). But **answers** fall back to
  deterministic *extractive* text whenever no chat provider is configured: `make_caller()` returns
  `None` when none of `anthropic_api_key` / `openai_api_key` / `model_endpoint` / `model_manifests`
  is set, so `FallbackAnswerGenerator` produces extractive answers. The `/query` path the SPA uses
  doesn't surface any signal that no model was used, and provider keys are env-only with no operator
  surface.
- **I3 — "no TDLib / Google / other auth."** *Implemented but disabled/invisible.* The Google OAuth
  flow (`/oauth/...`) and Telegram TDLib login (`/telegram/tdlib/connect`) are fully built but gated
  on config — Google needs `google_client_id/secret/redirect_uri`; TDLib needs
  `telegram_api_id/hash` plus a built `libtdjson`. Unconfigured, `authorize` returns a 409 while the
  catalog still lists every connector, so the UI shows a "Connect" button that just errors.

---

## Epic I1 — Delete uploaded documents

### I1.1 — List a workspace's uploaded documents · `CORE`+`GW` · `M`
`Workspace.list_documents()` returns the workspace's uploaded, non-tombstoned raw artifacts
(artifact id, filename, media type, byte size, claim/segment counts, created-at) — keyed on the
`upload` connector provenance so connector-synced artifacts are not shown here. New
`GET /workspaces/{ws}/documents` (workspace-writer gated).
Acceptance: after uploading N files, the endpoint returns N rows with stable artifact ids; an
erased document no longer appears.
Depends: —

### I1.2 — Delete an uploaded document · `GW` · `S`
`DELETE /workspaces/{ws}/documents/{artifact_id}` resolves the artifact *within the workspace*
(isolation guard → 404 otherwise) and calls the existing `erase_artifact` (tombstone cascade + blob
delete). Workspace-writer gated (uploads are a per-member action, unlike operator-gated connector
sources).
Acceptance: deleting an uploaded document tombstones its claims/mem-cells and erases its blob;
erased content stops appearing in answers/evidence; deleting another workspace's id is a 404.
Depends: I1.1

### I1.3 — Uploaded-documents UI with per-document delete · `FE` · `M`
A "Documents in this workspace" list under the upload dropzone (member-visible, not operator-gated):
filename + parse summary + a Delete with a non-default confirm reusing the erasure messaging.
Acceptance: a user who uploaded a PDF sees it listed and can delete it from the workspace without
operator access; the list refreshes after upload and after delete.
Depends: I1.1, I1.2

---

## Epic I2 — LLM answer visibility + runtime provider config

### I2.1 — Answer-mode on the query response · `GW` · `S`
Add `answer_mode` (`model` | `extractive`) to the `/query` and `/workspaces/{ws}/query` responses,
derived from whether a model caller was wired for the answering workspace. Extractive = no chat
provider configured (or a model error fell back).
Acceptance: with no provider configured the response reports `extractive`; with one configured and
healthy it reports `model`. No provider/model name leaks.
Depends: —

### I2.2 — "Answered without a model" UI note · `FE` · `S`
A quiet, non-alarming note on the answer when `answer_mode === "extractive"`, with a one-line "an
operator can connect a model in Settings → Operations" pointer (operator-routed, not a user dead
end). Distinct from the existing routing-outcome note.
Acceptance: an extractive answer renders the note; a model answer does not.
Depends: I2.1

### I2.3 — Durable deployment config store · `GW`+`CORE` · `M`
A durable, encrypted-at-rest `DeploymentConfigStore` over the existing secret store (Postgres;
in-memory for the dev backend) holding operator-set overrides: chat provider keys (Anthropic /
OpenAI-compatible), OpenAI base URL + chat model, local `model_endpoint` + chat model, and the I3
connector-auth credentials. **Embeddings are out of runtime scope** — changing an embedding model is
a re-index under the version-gating invariant, so it stays env-config (documented). Effective
settings = env `GatewaySettings` overlaid with the stored overrides at backend build.
Acceptance: a stored override survives restart and is shared gateway↔worker; secrets are encrypted
at rest.
Depends: —

### I2.4 — Operator config + status API · `GW` · `M`
`GET /admin/config` returns the effective config with **secrets masked** (set/unset, last-4 only)
plus a status block: chat-provider configured?, embeddings source, Google OAuth configured?,
Telegram TDLib configured?, `libtdjson` present?. `PUT /admin/config` validates + persists overrides
and **applies them to the live backend** by rebuilding the chat model plane + OAuth/Telegram wiring
in place (no embedding/engine churn; no process restart). Operator-principal gated.
Acceptance: an operator sets an Anthropic key via `PUT` and the next answer reports `answer_mode:
model` without a redeploy; `GET` never returns a full secret.
Depends: I2.3

### I2.5 — Operator "Model providers" config UI · `FE` · `M`
In Settings → Operations: show provider status; let an operator set/clear chat provider keys +
endpoints; show masked current values. No secrets shown back after entry.
Acceptance: an operator connects a provider from the console and sees status flip to configured;
keys are never re-displayed.
Depends: I2.4

---

## Epic I3 — Connector-auth availability + runtime config

### I3.1 — Connector availability in the catalog · `GW` · `S`
`GET /sources/connectors` reports per-connector `available` + a reason: an `oauth2` connector is
available only when Google OAuth is configured; `telegram` reports whether the bot token and/or
TDLib login is configured. Computed from the effective config (I2.3).
Acceptance: with Google unconfigured, `gdrive`/`gmail`/`calendar` report `available: false` with a
reason; configuring Google flips them to available.
Depends: I2.3

### I3.2 — Catalog UI reflects availability · `FE` · `S`
The add-source form disables/annotates connectors that aren't configured on this deployment ("Not
configured — an operator can enable this in Settings → Operations") instead of offering a Connect
button that 409s.
Acceptance: an unconfigured connector is shown as unavailable with the operator pointer, not a
broken button.
Depends: I3.1

### I3.3 — Runtime Google OAuth + Telegram credentials · `GW`+`FE` · `M`
Extend `PUT /admin/config` (I2.4) with the Google OAuth client (id/secret/redirect/scopes) and the
Telegram app credentials (api id/hash). Applying rebuilds `backend.google_oauth` /
`backend.telegram_connect` in place. Operator UI fields under Operations. `libtdjson` build stays an
ops/deploy step (documented), surfaced as a status flag.
Acceptance: an operator enters a Google client id/secret and the OAuth connectors become available
and complete a consent without a redeploy.
Depends: I3.1, I2.4

### I3.4 — Configuration docs · `docs` · `S`
A deployment configuration guide: chat/embedding providers (env + runtime), Google OAuth client
setup + redirect URI, Telegram bot vs TDLib (api id/hash + building `libtdjson` via the opt-in
compose profile), and the embeddings-are-a-re-index caveat.
Acceptance: an operator can enable each capability by following the doc.
Depends: —

---

## Suggested build order

1. **I1** (I1.1 → I1.2 → I1.3) — the one genuinely missing feature; self-contained.
2. **I2.1 → I2.2** — make the no-model state visible (smallest honest fix).
3. **I2.3 → I2.4 → I3.1** — durable config + status + connector availability (the read/diagnosis side).
4. **I2.5 → I3.2 → I3.3** — the operator config UIs + runtime apply (the write side).
5. **I3.4** — docs.

---

## Follow-ups (discovered during implementation)

### F1 — Runtime provider config doesn't reach the ingest/runtime workers · `GW`+`deploy` · `M`
The runtime provider config (I2.4) and its live `reconfigure_models` apply to the **gateway's
answering model plane only**. The ingest worker (OCR/vision transcription for low-coverage PDFs) and
the runtime worker (deep research via the query engine) each build their own model plane from their
**own env settings** (`METIS_INGEST_WORKER_*` / `METIS_RUNTIME_WORKER_*`) and do not read the shared
`DeploymentConfigStore`. So a provider key an operator sets in Settings → Providers reaches gateway
answers but **not** worker OCR or research.

The override is already durable + cross-process (the shared `connector_secrets` table, `cfg:` prefix)
— the workers just don't consult it. Approach: on worker startup build a `DeploymentConfigStore` over
the same secret store and overlay settings via `effective_settings(...)` (the gateway's overlay).
Workers are separate processes with no live-reconfigure path, so **apply-on-startup** (picked up on
restart) is the simplest; re-read per job-lease only if closer-to-live propagation is needed. Requires
the cred-store key wired per worker that consumes the store — the ingest worker is base-wired (as of
the base-compose change); the runtime worker would need
`METIS_RUNTIME_WORKER_CRED_STORE_KEY: ${METIS_CRED_STORE_KEY:-}` added.

Invariants: embeddings stay env-only (re-index under version-gating, ADR 0014 — never route embedding
config here); secrets stay encrypted at rest (reuse the existing `SecretStore`).

Acceptance: a provider key set via `PUT /admin/config` (cred key wired) is used by the ingest worker's
OCR and the runtime worker's research after a worker restart, without editing per-worker env.
Depends: I2.4
