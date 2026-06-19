# Server Deployment Product Roadmap

Reviewed: 2026-06-19. Grounded in a read of the current tree (`packages/`, `services/`,
`deploy/`), so "already built" and "still missing" below reflect the code, not aspiration.

This plan turns Metis from an evidence-first workspace memory engine into a small
production deployment for about 10 people. The first target is one organization with
personal and shared context workspaces, live email and document ingestion, cloud LLM and
embedding APIs by default, and a clean path to plug in a rented GPU running open
Hugging Face models. Later stages add more connectors, safer browser-based skills, and a
federation layer between two deployed Metis servers.

The product is useful because it gives a team a durable **context exoskeleton**: a
structured external memory for work artifacts, not a chatbot over a vector store. It
remembers what was imported, cites the raw evidence behind every answer, separates personal
from shared context, surfaces contradictions instead of silently overwriting, and lets the
underlying models change without losing the organization's knowledge substrate.

## Strategic Stance

1. **Ship cloud API first.** For 10 users, hosted LLM and embedding APIs are simpler, more
   reliable, and easier to evaluate than operating GPUs on day one.
2. **Keep model serving swappable.** Treat OpenAI, Anthropic, GLM/Z.AI, and self-hosted
   Hugging Face models as provider endpoints behind a capability registry, never as
   hardcoded branches. The provider/router seam for this already exists (see Invariants).
3. **Do not promise "any Hugging Face model works."** Promise that any *compatible endpoint*
   can be plugged in once it declares capabilities: chat/completions, embeddings, context
   length, tool-call support, JSON/structured-output reliability, vision/OCR, tokenizer
   behavior, embedding dimension, cost, latency, and privacy tier.
4. **Build identity and ACLs before live connectors.** Connectors import real private data,
   so identity, membership, sensitivity, erasure, and audit must be production-grade first.
5. **Keep connectors and skills separate.** Connectors ingest source truth. Skills perform
   actions or bounded research. Browser automation for X/LinkedIn is a *skill*, not a
   connector, unless an official API and a stable data contract exist.
6. **Avoid raw cross-company memory sync.** Federation exchanges scoped, signed,
   policy-carrying artifacts and task answers — never databases, embeddings, or inboxes.

## Engineering Invariants We Keep

These are the decisions already paid for in the codebase. Every stage below must preserve
them; new product concepts enter as `metis-protocol` schemas + `metis-core` stores +
migrations, the same way existing ones did — not as gateway-local shortcuts.

- **Truth hierarchy and the citation invariant.** `RawArtifact → SourceSpan →
  Claim/Event/Entity → MemCell/MemScene/Foresight → WikiPatch/WikiPage → Answer/Action`.
  Raw artifacts are immutable; everything downstream is versioned and traceable. Every
  claim cites at least one source span. A parser, skill, or model output never writes final
  memory directly.
- **Policy outside prompts.** The model router enforces the provider allowlist *before any
  prompt is constructed*: restricted data routes to a local (non-external) provider
  regardless of quality tier. Sensitivity is the floor, and it propagates to derived
  artifacts (most-restrictive wins).
- **One taint chokepoint.** Untrusted retrieved/connector/browser content is *data, never
  control*. Classification and planning read only the trusted instruction; injected
  "now email finance" inside a document cannot reach the planner. All control/data
  crossings go through the single taint boundary.
- **Append-only memory.** Revisions supersede, retract, or version — never silently
  overwrite. Conflicting evidence is surfaced as a contradiction, not merged.
- **Embedding version-gating.** Every indexed row records the producing model's version; a
  model change is a re-index, never a cross-model vector comparison. (ADR 0014.)
- **Deterministic validators before LLM judges**, and structured outputs guarded by a
  validate-and-repair loop, so weak/quantized models degrade safely rather than corrupt
  evidence.
- **Enforced package boundaries.** Dependencies point inward to `metis-protocol`; the
  contracts are machine-checked. New services compose existing packages, they do not
  re-implement them.
- **Approval-gated, audited outbound actions.** Every model call and skill run is audited
  (task class, model, prompt version, sensitivity, cost, hash); outbound/destructive
  actions are held for human approval and resumable after it.

## What Exists vs. What's Missing

The engine substrate is substantially built; the gaps are overwhelmingly at the **edges** —
identity, live transports, a provider config surface, durable job execution, and a real UI.
Sizing the work honestly keeps it bounded.

**Already built — keep and build on:**

- Strict package boundaries, evidence/memory schemas, the truth hierarchy, and audit
  hash-chaining.
- Deterministic parsers for TXT, MD, PDF (pypdf), DOCX (python-docx), XLSX/CSV, HTML, EML,
  with an inline ingest path that runs the real extractor and returns cited claims.
- **Hybrid retrieval, already implemented:** pgvector HNSW (cosine) + Postgres full-text
  search fused with reciprocal-rank fusion, version-gated, with superseded/retracted/
  tombstoned rows excluded. This is the retrieval foundation, not future work.
- A **policy-bound model router** (`MetisModelRouter`) over real provider adapters:
  `AnthropicProvider` (SDK), `OpenAICompatProvider` (OpenAI / Ollama / vLLM / TGI and any
  OpenAI-compatible endpoint), and a deterministic `StubProvider` for CI/restricted data.
- A skill runtime: manifest security contract, subprocess sandbox, deny-by-default
  permissions, approval-by-default for outbound actions, audited artifact capture, plus a
  working sandboxed `web_search` skill.
- The agent loop with control/data-plane separation and resumable, approval-gated runs.
- A durable Postgres backend (stores, object store, memory index, audit) behind the same
  seams as the in-memory backend; Alembic migrations; single-node Compose stack with
  backup/restore and an OpenTelemetry surface.
- A deterministic, Docker-free evaluation harness with regression thresholds (safety
  dimensions pinned at 1.0).

**Gaps to close — product and operations:**

- **Production auth is missing.** Gateway auth is dev-token based, not user / organization /
  workspace / membership based.
- **Multi-workspace lives in the data model but not the edge.** Every store query already
  filters by `workspace_id`; the gateway just pins one configured workspace and uses global
  tokens. Isolation is enforced in storage, not yet in identity.
- **Connectors are replay-only.** The connector *logic* (IMAP thread reconstruction,
  cursors, token-bucket rate limiting, retry/backoff) is real and tested, but the only
  `Transport` implementation is `RecordedTransport`. No live transport (imaplib, HTTP SDK,
  Google API) exists, so nothing syncs a real mailbox or drive. The IMAP connector also
  reads `text/plain` bodies only — no attachment extraction yet.
- **No autonomous job execution.** The maintainer worker has a poll loop, but the ingest and
  runtime workers are wire-and-stop stubs, and both gateway backends use an in-memory job
  queue. Ingestion works inline via the API; there is no scheduled connector sync or
  background maintenance running on a timer.
- **Some gateway state is in-memory in both backends:** the job queue, wiki inbox, and
  approval inbox. Only the Postgres backend persists stores and audit. Server-grade
  approval/wiki/job surfaces must become durable.
- **Cloud providers are not configurable through the gateway.** The router and adapters
  exist, but `build_model_caller` wires a single local Ollama endpoint, and `GatewaySettings`
  has no API-key/provider fields. Production needs a first-class provider config surface,
  not new adapters.
- **Production PDF quality.** Deterministic parsing covers clean files; complex layouts,
  tables, and scanned PDFs need layout-aware parsing, OCR fallback, and parse-quality
  diagnostics.
- **No reranker** (a noted "add later" stand-in) and **no OAuth / Google connectors** yet.
- **The UI is a debug console**, not a 10-user workspace product.

## Stage 1: Ten-User Server Deployment

Detailed plan: [server-deployment-stage-1.md](server-deployment-stage-1.md).

Goal: one company server, 10 users, each with a personal workspace and access to one or more
shared workspaces, using cloud LLM and embedding APIs first.

### 1.1 Production Deployment Foundation

A single-node profile that can later split into managed services:

- Gateway, ingest worker, maintainer worker, runtime worker.
- Postgres with the **pgvector** extension (already required by the memory index) for
  metadata, jobs, memory, and retrieval.
- S3-compatible object storage: MinIO on the node or managed object storage.
- Migrations as a single init step, not per-service races.
- TLS termination, domain routing, backups, restore drills, log retention, OpenTelemetry
  traces.
- Operator dashboards: failed jobs, ingestion lag, model spend, policy denials, parser
  failures, connector rate limits.
- Hard resource budgets: max document size, max job runtime, max model spend per workspace,
  max skill runtime, max browser sessions.

Reasonable first deployment: one small cloud VM for app services; managed Postgres if budget
allows, otherwise local Postgres with tested backups; managed object storage or MinIO with a
tested restore; cloud LLM and embedding APIs by default. GPU is **optional** here — a GPU
marketplace (Vast.ai or similar) is an escape hatch for experiments or privacy/cost
pressure, not the reliability foundation.

### 1.2 Identity, Workspaces, and ACLs

Add first-class product identity as protocol schemas + core stores + migrations:

`Organization`, `User`, `WorkspaceMembership`, `WorkspaceKind` (personal, shared,
external/federated later), `Role` (owner, admin, member, viewer, auditor), `SourceConfig`,
`SourceCredentialRef`, `SourceCursor`, `ConnectorRun`, `ModelProviderConfig`,
`WorkspaceModelPolicy`. (`Workspace` already exists in the substrate.)

Rules:

- Every user gets a personal workspace. Shared workspaces are explicit, never a side effect
  of the organization.
- A query can target personal, shared, or mixed context, and the UI makes the active scope
  visible.
- Membership is checked **before** any retrieval touches spans, claims, memory, wiki, or
  artifacts — extending the existing `workspace_id` storage filter up into identity.
- Source ACLs are a floor for sensitivity: unknown or private ACLs map *more* restrictive,
  never less.
- Audit events carry real actor identity, workspace, source, model provider, skill, and
  policy decision.

This is the **first hard gate**: live connectors stay disabled until workspace-isolation
tests pass (including a negative test that one user cannot read another's personal context).

### 1.3 Model and Embedding Provider Plane

Promote the existing router into a configurable registry instead of one-off env vars:

- **Chat/generation:** OpenAI-compatible, Anthropic, GLM/Z.AI, local Ollama, vLLM, TGI.
- **Embeddings:** OpenAI-compatible, Hugging Face TEI, Ollama, provider-specific APIs.
- **Rerank:** local or TEI rerank endpoint (optional in Stage 1).
- **`ModelCapability` descriptor per deployed model** (a protocol schema), so routing and
  budgets are capability-driven, not name-driven.
- **`WorkspaceModelPolicy`:** whether external providers may see a given source's content
  (enforced by the router's existing pre-prompt allowlist).
- **Spend tracking per task class:** ingestion extraction, query answer, deep research,
  summarization, rerank, OCR/VLM.

Recommended model roles:

- **Embedding model** — stable, cheap, versioned; changing it triggers a re-index (already
  enforced by version-gating).
- **Reranker** — optional in Stage 1; useful once retrieval errors dominate.
- **Small control model** — query rewrite, classification, tool/skill selection.
- **Main answer model** — chat with citations.
- **Deep research model** — larger context, stronger reasoning, budget-limited.
- **Document vision/OCR model** — only for scanned PDFs and layout-heavy files.

For Hugging Face on rented GPUs:

- Serve chat behind vLLM or TGI; serve embedding/rerank behind TEI.
- Expose them as private OpenAI-compatible URLs — they plug straight into the existing
  `OpenAICompatProvider`, so this is configuration, not a new adapter.
- Require a **model manifest** before enabling a model: `model_id`, endpoint type, context
  window, max output, tokenizer, supported params, tool/JSON support and structured-output
  reliability, embedding dimension, hardware, quantization, expected latency, privacy tier.
- Keep cloud fallback active for failed GPU instances (the router already supports an
  ordered provider list with local/cloud fallback).

Anti-goals:

- Do not build direct adapters for every model repo on Hugging Face.
- Do not auto-select models by name: some are base (not chat) models, some need special
  templates, some cannot follow tool schemas, and embedding dimension is bound to the index.
- Do not fine-tune on private company data in Stage 1 — retrieval and memory quality matter
  more, and fine-tuning creates governance risk.

### 1.4 Live Ingestion for Email and Documents

Stage 1 ingestion should be boring, reliable, and auditable. The connector spine, cursors,
and rate limiting already exist behind the `Transport` seam; this stage writes the live
transports.

Email:

- IMAP connector with a live `ImapTransport` (imaplib), OAuth where possible and
  app-password/basic auth only when explicitly allowed.
- Gmail as a Google API connector — not plain IMAP — where Workspace ACLs, labels, and
  shared mailboxes matter.
- Add **attachment extraction** (the current connector is text-body only), plus
  sender/recipient metadata, date watermarks, idempotent raw-artifact keys, and cursor
  persistence. Thread reconstruction already works.
- Per-user mail defaults to the personal workspace; shared mailboxes can feed shared
  workspaces.

Documents:

- File upload API and UI for PDF, DOCX, XLSX, CSV, TXT, MD, HTML, EML.
- Batch upload with progress, visible parse failures, and retry.
- Google Drive connector: OAuth, shared drives, folder selection, export for
  Docs/Sheets/Slides, file revisions, ACL-to-sensitivity mapping. Common folders feed
  shared workspaces; personal folders feed personal workspaces.
- Parser quality reports: text coverage, table/page counts, OCR fallback, warnings,
  unsupported elements.

Parsing upgrades:

- Keep the deterministic parsers for simple files.
- Add a layout-aware path for complex PDFs and office documents.
- Use OCR/VLM only when deterministic parsing fails or coverage is low.
- Preserve the invariant: `raw artifact → parsed doc → segment → claim/event/entity →
  memory`. A parser never writes final memory.

### 1.5 Context Exoskeleton Product Surface

The product is managed context, not "chat with files."

Core surfaces:

- **Workspace switcher:** personal, shared, mixed (active scope always visible).
- **Source dashboard:** connected accounts, folders, mailboxes, sync state, errors.
- **Evidence browser:** raw artifact → source spans → claims → memory cells → wiki page.
- **Chat/research with citations** and a "why this answer" evidence trail.
- **Contradiction inbox:** new evidence conflicting with existing memory.
- **Memory review:** accept, retract, or mark stale important user/profile/company facts.
- **Wiki projection:** compiled, human-readable pages with provenance.
- **Erasure flow:** delete a source or user and propagate removal/tombstones to derived
  artifacts.

State-of-the-art direction:

- Treat memory as a **write / manage / read loop**, not a vector store.
- Decompose repetitive source material into reusable facts/components before aggregating
  into summaries, so memory stays composable rather than a pile of chunks.
- For deep research and long tasks, keep **execution state separate from semantic memory**
  so failed branches and stale findings do not pollute current context.
- Lead with hybrid retrieval (lexical + vector + provenance filters, optional reranker) —
  which already exists — and add graph/community retrieval only when evaluation shows
  multi-hop questions need it.

### 1.6 API and UI Deliverables

API:

- User/session; workspace CRUD and membership.
- Source configuration and OAuth callback.
- File upload and connector sync.
- Query/chat/research with workspace selection and citations.
- Job inspect/retry/cancel.
- Audit.
- Provider config and spend (operators).

UI:

- Login and workspace switcher.
- Source setup for email, Google Drive, and file upload.
- Chat/research with citations and evidence drilldown.
- Jobs/errors dashboard.
- Approval and contradiction inbox.
- Provider/spend dashboard (operators).

Acceptance criteria (each independently testable):

- 10 users can log in; each has a personal workspace; users can join a shared workspace.
- A shared Google Drive folder and a personal email source ingest end to end via a queued
  connector job (not an inline POST).
- PDF, DOCX, XLSX/CSV, TXT/MD, HTML, and EML files ingest with visible parse status.
- Queries can target personal, shared, or mixed context, and answers cite source-backed
  evidence.
- A user **cannot** retrieve another user's personal context (enforced and tested).
- Cloud LLM and embedding providers are configurable without code edits.
- A Hugging Face model served behind TGI/vLLM/TEI registers via its capability manifest.
- Backups restore a small fixture deployment.
- Model spend and connector failures are visible to operators.

## Stage 2: Connectors, Skills, and Deep Research

Detailed plan: [server-deployment-stage-2.md](server-deployment-stage-2.md).

Goal: expand data reach and action capability without weakening source truth, policy, or
audit.

### 2.1 Connectors Before Browser Automation

Prioritize official APIs and stable exports:

- Slack or Microsoft Teams.
- Google Calendar and/or CalDAV.
- Notion and Confluence.
- GitHub/GitLab issues, PRs, discussions, repos.
- SharePoint/OneDrive for Microsoft 365 users.
- Web clipper and URL fetcher; RSS/news.
- CRM/helpdesk only on clear user need.

Connector rule: if the source has an official API and a stable permission model, build a
connector; if it needs a logged-in browser, treat it as a skill with explicit approval,
short-lived scope, and visible artifacts.

### 2.2 Browser Skills for Authenticated Sources

LinkedIn, X, and similar platforms are poor first-stage connectors because APIs, terms,
anti-automation systems, and account-risk policies change. A browser skill can still serve
user-directed research if designed as controlled remote work:

- Playwright (or a browser service) inside a stronger sandbox profile.
- Browser auth state stored as a secret-grade artifact — never in git or normal object
  storage.
- User-initiated login and domain allowlists; per-run approval for collection scope.
- Save screenshots, URLs, timestamps, and extracted snippets as evidence.
- Never silently post, message, follow, like, or mutate account state.
- Rate-limit and stop on CAPTCHA or unusual-account-risk signals.
- Outputs reviewable before ingestion into memory.

Anti-goals:

- A "LinkedIn connector" that scrapes at scale as a background job.
- Driving a logged-in browser without a typed task contract.
- Letting browser-captured content become trusted instructions (the taint boundary holds
  here too).

### 2.3 Deep Research Skill

Upgrade the single-shot web search into a research workflow with an explicit task tree and
budgets:

- **Plan:** turn the request into research questions, candidate sources, and stop
  conditions.
- **Search:** multiple providers/APIs for source diversity.
- **Fetch:** browser or HTTP fetch with content extraction.
- **Triage:** credibility, recency, duplicates, conflict detection.
- **Read:** extract claims with source spans (same citation invariant as ingestion).
- **Synthesize:** a cited brief, not snippets.
- **Persist:** optionally ingest approved findings as external-source artifacts.
- **Budget:** cap searches, pages, model tokens, browser time, and wall-clock.
- **State:** a task tree so failed branches and stale findings do not pollute active
  context (execution state, kept separate from semantic memory).

Output: a research artifact with citations, confidence, unresolved questions, and a
machine-readable claim set.

### 2.4 Skill Platform

- Signed skill packages; dependency lockfiles and reproducible environments.
- Stronger sandbox profiles for browser/network skills.
- A skill secrets broker with per-skill scopes.
- Reviewable, ingestible artifact outputs; human approval for side effects.
- Skill evaluation fixtures, including prompt-injection and data-exfiltration tests.
- Optional MCP client/server support so Metis can expose selected tools/context and consume
  external tools without bespoke integrations.

## Stage 3: Server-to-Server Context Exchange

Detailed plan: [server-deployment-stage-3.md](server-deployment-stage-3.md).

Goal: two companies running separate Metis deployments can collaborate without merging
databases or exposing private workspaces.

### 3.1 Direction: Federation, Not Raw Sync

Expose a company server as a policy-aware agent with: a public capability card, an
authenticated extended capability card, a scoped task API, export/import of signed evidence
packages, a federated query API, and a usage ledger with rate limits.

A2A fits task exchange between independent agent systems (discovery, task lifecycle,
messages, artifacts, streaming, push, auth). MCP fits exposing tools/resources to an LLM
application. Use both: A2A for server-to-server collaboration, MCP for selected tool/context
exposure.

### 3.2 Exchange Objects

Metis-native objects mapping onto A2A artifacts or MCP resources:

- `CapabilityCard` — what this server can answer or do.
- `ContextOffer` — what context can be shared, under what terms.
- `ContextRequest` — scoped request for an answer, evidence, digest, or artifact.
- `EvidencePackage` — redacted source spans, claims, provenance, sensitivity, license,
  expiry, signature.
- `WikiDigest` — a compiled page subset with source-backed references.
- `AnswerArtifact` — answer plus citations, confidence, cost, policy.
- `RevocationNotice` — invalidates a shared package or grant.
- `UsageLedgerEntry` — billable units, task IDs, evidence IDs, timestamps.

Default exchange policy: no personal workspaces, no raw inboxes, no raw embeddings, no
connector credentials, no silent onward sharing — redacted snippets and claims only unless a
human approves more.

### 3.3 Federation Phases

1. **Manual export/import** — operator exports a signed evidence package; the other server
   imports it into an external/federated workspace. Best first step: it tests schemas,
   redaction, signatures, and audit.
2. **Federated query** — Company A asks Company B a scoped question; B answers with citations
   or refuses; A stores the answer artifact and optional evidence package.
3. **Shared workroom** — both agree on a shared external project context; selected packages
   and wiki digests replicate with TTL and revocation; conflicts stay explicit, never
   auto-merged into canonical memory.
4. **Paid exchange** — quotas, invoicing, prepaid credits, data-use licenses, usage ledger —
   only after trust, audit, quality, and legal workflows are proven.

Anti-goals: payment rails before access control and evidence quality; peer-to-peer database
replication; exchanging embeddings as if anonymized; one company's agent acting in another's
systems without explicit task-level authorization.

### 3.4 Federation Security Requirements

- Organization identity via OIDC client credentials and/or mTLS.
- Signed capability cards and evidence packages.
- Tenant-specific rate limits and quotas.
- Policy checks before any query that could reveal object existence.
- Redaction and PII scanning before export.
- Expiry, revocation, and deletion propagation.
- Legal metadata: owner, license, allowed use, retention, onward-sharing rules.
- Audit trails both sides can reconcile by task ID and package hash.

## Implementation Order

Grouped into milestones; the numbering is the global build sequence.

1. **Milestone A — multi-user and durable (the first hard gate).** Production auth and
   workspace membership.
2. Durable source configs, credentials, cursors, connector runs, approvals, wiki, and job
   state.
3. Cloud LLM and embedding provider registry with capability manifests.
4. **Milestone B — make data flow.** File upload product flow.
5. Live IMAP/Gmail and Google Drive ingestion (live transports behind the existing seam).
6. Ingest/runtime worker queue dispatchers (replace the in-memory queue; turn the stubs
   into real loops).
7. **Milestone C — make it usable.** Evidence-rich UI for chat, sources, jobs, approvals,
   and spend.
8. Parser quality upgrades for complex PDFs and spreadsheets.
9. Hugging Face endpoint support through TGI/vLLM/TEI manifests.
10. **Milestone D — expand reach.** Deep research skill.
11. Additional official connectors.
12. Browser skill for authenticated web research.
13. **Milestone E — federate.** Manual signed export/import.
14. Federated query and shared workroom.
15. Paid context exchange.

## Key Risks

- **ACL leakage is the existential risk.** One cross-user leak makes the product unusable
  for teams. Storage already filters by workspace; the new identity layer must not introduce
  a path around it.
- **Connector auth and token refresh** will cost more engineering than the parser code.
- **Browser automation is fragile and legally sensitive** — keep it user-driven and
  artifact-focused.
- **"Any model" support becomes unbounded** unless capabilities are explicit; the capability
  manifest is the control.
- **Deep research loops grow cost quickly** without task budgets; cap tokens, pages, and
  wall-clock per run.
- **GraphRAG can become expensive overengineering.** Hybrid retrieval and wiki memory
  already exist; add graph retrieval only when evals show they are insufficient.
- **Federation is mostly governance, not transport.** A2A/MCP shape interoperability but do
  not solve data rights, trust, pricing, or erasure.

## References

Local project references:

- [Frontier approaches](../references/frontier-approaches.md)
- [Stage 11 connectors](stage-11-connectors.md)
- [Stage 12 API/UI/ops](stage-12-api-ui-ops.md)
- [Stage 15 deployment](stage-15-deployment.md)
- [ADR 0020 external connectors](../adr/0020-external-connectors-and-replayable-ingestion.md)

Protocol and serving specs (verified):

- [A2A Protocol specification](https://a2a-protocol.org/latest/specification/)
- [Model Context Protocol specification](https://modelcontextprotocol.io/specification/2025-06-18)
- [Hugging Face TGI — OpenAI-compatible chat serving](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/consuming_tgi)
- [Hugging Face TEI — embeddings/rerank serving](https://huggingface.co/docs/text-embeddings-inference/quick_tour)
- [Vast.ai GPU marketplace](https://docs.vast.ai/guides/get-started)
- [Playwright authentication state](https://playwright.dev/docs/auth)

Research directions that shaped this plan (confirm citations before any external use — the
arXiv IDs below were drafted from notes and are not yet verified):

- Provider-API translation as a portability layer for swappable model endpoints
  (cf. "LLM-Rosetta", arXiv 2604.09360 — to verify).
- Memory beyond flat RAG: a managed write/manage/read loop for agent memory
  (cf. "xMemory", arXiv 2602.02007 — to verify).
- Memory as execution-state management for long-horizon agents
  (arXiv 2606.06090 — to verify).
- Agent interoperability protocol survey (arXiv 2505.02279 — to verify).
