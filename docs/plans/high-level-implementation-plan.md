# Metis High-Level Implementation Plan

This is the top-level implementation plan for building Metis with agent-assisted development. It intentionally avoids time estimates. Detailed execution plans for each stage are maintained separately under `docs/plans/`, linked from each stage heading below and indexed under [Detailed Plans](#detailed-plans).

The product goal is a workspace memory/context engine: evidence-first ingestion, structured memory, background maintenance, compiled wiki projection, retrieval/chat, and skill-based actions.

Companion references: [`package-decomposition.md`](../package-decomposition.md) for package responsibilities and swappable-interface ownership, and [`references/`](../references/README.md) for the research and engineering references that shape the architecture.

## Guiding Principles

1. Build one monorepo with multiple installable packages and strict import boundaries.
2. Treat raw artifacts and source spans as evidence truth.
3. Treat claims, entities, events, and memory objects as machine truth.
4. Treat wiki pages as compiled human-facing projections, not canonical machine truth.
5. Make every major block swappable through `metis-protocol` schemas, interfaces, and events.
6. Enforce policy outside prompts: data sensitivity, model routing, skill permissions, network access, filesystem access, and outbound actions.
7. Prefer deterministic validators before LLM judges.
8. Keep memory revision append-only: supersede, retract, and version rather than silently overwrite.
9. Build evaluation fixtures early enough that model and pipeline changes can be compared.
10. Optimize for correctness, provenance, and work quality before latency tricks.

## Target Monorepo Shape

```text
metis/
  packages/
    metis-protocol/
    metis-core/
    metis-ingestion/
    metis-maintainer/
    metis-runtime/
    metis-skills/
  services/
    gateway/
    ingest-worker/
    maintainer-worker/
    runtime-worker/
  eval/
  deploy/
  docs/
```

Dependency direction:

```text
metis-protocol
  used by everything
  imports no other Metis package

metis-core
  imports metis-protocol

metis-ingestion
  imports metis-protocol, metis-core

metis-maintainer
  imports metis-protocol, metis-core

metis-skills
  imports metis-protocol

metis-runtime
  imports metis-protocol, metis-core, metis-skills
```

`metis-ingestion` may additionally invoke `metis-skills` in a restricted, off-by-default ingestion-enrichment mode; that controlled edge is the only optional addition to the directions above.

## Stage 0: Repository And Architecture Guardrails

Detailed plan: [stage-00-repo-guardrails.md](stage-00-repo-guardrails.md)

Purpose: create the monorepo structure, package boundaries, developer commands, and architecture enforcement before domain logic grows.

Primary outputs:

- workspace package layout
- shared dev tooling
- import-boundary checks
- baseline test runner
- lint/typecheck/format commands
- initial documentation index
- architecture decision records for major choices

Key decisions:

- Python packaging/workspace tool
- test framework
- import boundary enforcement
- service entrypoint convention
- configuration convention

Validation:

- packages install locally
- tests run from repo root
- forbidden imports fail CI
- docs describe package ownership

## Stage 1: `metis-protocol`

Detailed plan: [stage-01-protocol.md](stage-01-protocol.md)

Purpose: define the shared language of the system.

Primary outputs:

- core IDs and typed references
- artifact schemas
- source, connector, parser, extraction, memory, wiki, query, skill, and audit schemas
- event envelope and event names
- policy vocabulary
- provenance model
- model task classes
- protocol interfaces
- schema versioning pattern
- contract test helpers

Core schemas:

```text
RawArtifact
NormalizedDoc
ParsedDoc
Segment
SourceSpan
Claim
Entity
Event
ExtractionBatch
MemCell
MemScene
Profile
Foresight
Contradiction
MemoryPatch
WikiPatch
WikiPage
QueryRequest
EvidenceSet
ContextBundle
SkillManifest
SkillInput
SkillResult
AuditEvent
```

Core interfaces:

```text
Connector
Parser
Extractor
Consolidator
ContradictionDetector
ForesightBuilder
ArtifactStore
DocumentStore
ClaimStore
MemoryStore
WikiStore
AuditSink
ModelProvider
ModelRouter
Retriever
ContextPacker
Skill
SkillRunner
```

Validation:

- schemas round-trip through JSON
- event envelopes are versioned
- every artifact can carry provenance and policy
- no protocol object depends on storage implementation details

## Stage 2: `metis-core`

Detailed plan: [stage-02-core.md](stage-02-core.md)

Purpose: implement durable storage, audit, jobs, and policy enforcement surfaces.

Primary outputs:

- database schema and migrations
- object storage abstraction
- artifact store
- normalized document store
- parsed document/segment store
- claim/entity/event store
- memory store
- wiki patch store
- audit log
- job queue
- policy decision helpers
- local development database setup

Truth hierarchy:

```text
RawArtifact -> SourceSpan -> Claim/Event/Entity -> MemCell/MemScene/Foresight -> WikiPatch/WikiPage -> Answer/ActionArtifact
```

Important constraints:

- raw artifacts are immutable
- derived artifacts are versioned
- memory revision is append-only
- wiki writes happen through patches
- audit events are emitted for model calls, skill runs, storage writes, policy decisions, and outbound actions

Validation:

- migrations apply from empty database
- stores pass protocol contract tests
- artifacts can be traced back to raw source spans
- deletion/tombstone flow works on a small fixture
- policy decisions are testable without an LLM

## Stage 3: Local-First Ingestion Pipeline

Detailed plan: [stage-03-ingestion.md](stage-03-ingestion.md)

Purpose: ingest files into structured evidence with high-quality provenance.

Primary outputs:

- local folder connector
- raw artifact ingestion
- MIME/type detection
- parser registry
- document parsing for common file types
- segmentation
- source-span mapping
- baseline extraction into claims/entities/events
- ingestion job orchestration
- ingestion fixtures

Initial file types:

```text
txt
md
pdf
docx
xlsx/csv
html
eml
```

Pipeline:

```text
discover -> fetch -> store raw -> normalize -> parse -> segment -> extract -> validate -> write evidence
```

Validation:

- each extracted claim cites source spans
- parser failures are recorded without stopping the pipeline
- duplicate artifacts are idempotent
- extracted evidence survives re-run without duplicate logical facts
- fixture ingest produces deterministic enough outputs for regression tests

## Stage 4: Model Router And Extraction Quality Loop

Detailed plan: [stage-04-model-router.md](stage-04-model-router.md)

Purpose: make LLM calls swappable, policy-bound, measurable, and suitable for structured extraction.

Primary outputs:

- model provider adapters
- router policy config
- task classes
- prompt registry
- structured-output validation
- retry/repair loop
- model-call audit logging
- budget and sensitivity enforcement
- extraction quality evals

Task classes:

```text
parse_assist
segment
extract_claims
extract_entities
extract_events
summarize_episode
consolidate_memory
detect_contradiction
build_foresight
wiki_compile
query_rewrite
query_answer
query_verify
skill_plan
skill_execute
```

Validation:

- restricted artifacts never route to disallowed providers
- prompts and model versions are logged
- malformed structured outputs are rejected or repaired
- local fallback works for restricted data
- extraction evals compare model/provider choices

## Stage 5: Memory Core

Detailed plan: [stage-05-memory-core.md](stage-05-memory-core.md)

Purpose: turn extracted evidence into long-lived, queryable workspace memory.

Primary outputs:

- MemCell generation
- MemScene clustering
- scene summaries
- profile/state summaries
- time-bounded foresight objects
- memory patch model
- supersession/retraction model
- memory retrieval indexes
- memory eval fixtures

Memory objects:

```text
MemCell = episode-like interpreted memory backed by claims/source spans
MemScene = thematic cluster of related MemCells and claims
Profile = stable workspace/user/company facts with conflict tracking
Foresight = expected future state with validity window and evidence
```

Validation:

- MemCells are traceable to claims and source spans
- scenes can be incrementally updated
- stale memories can be superseded
- conflicting evidence does not silently merge
- memory retrieval beats naive chunk retrieval on golden workspace questions

## Stage 6: Maintainer Worker

Detailed plan: [stage-06-maintainer.md](stage-06-maintainer.md)

Purpose: run background intelligence over memory and evidence.

Primary outputs:

- contradiction detector
- stale fact detector
- episode revision jobs
- scene refresh jobs
- profile refresh jobs
- foresight builder
- wiki patch proposer
- maintenance scheduler
- maintenance audit trail

Maintainer jobs:

```text
detect_contradictions
revise_episodes
refresh_scenes
refresh_profile
build_foresights
compile_wiki_patches
lint_wiki
validate_claim_support
validate_deletions
```

Validation:

- contradiction injection fixture is detected
- superseded memories remain auditable
- wiki patches cite claim IDs
- deletion/tombstone state propagates into derived artifacts
- maintainer jobs are idempotent

## Stage 7: Wiki Compiler And Human-Facing Knowledge

Detailed plan: [stage-07-wiki-compiler.md](stage-07-wiki-compiler.md)

Purpose: compile evidence and memory into navigable markdown without making the wiki the machine source of truth.

Primary outputs:

- wiki repository initialization
- page schema
- entity/topic/project pages
- index/log pages
- backlink generation
- wiki patch model
- patch validation
- patch approval/commit flow
- WiCER-style compile/evaluate/refine loop
- Error Book or equivalent correction memory

Wiki flow:

```text
claims + memory + existing pages -> proposed patch -> validators -> approval/commit -> index/search update
```

Validation:

- wiki statements cite claim IDs/source spans
- wiki patches fail if unsupported claims are introduced
- contradictions are surfaced rather than hidden
- page regeneration is stable enough for diffs
- wiki compilation loss is measured against diagnostic probes

## Stage 8: Retrieval And Query Runtime

Detailed plan: [stage-08-retrieval-runtime.md](stage-08-retrieval-runtime.md)

Purpose: answer user questions with sufficient, cited, policy-safe context.

Primary outputs:

- query API
- hybrid retriever
- memory retriever
- wiki retriever
- graph/link traversal where useful
- reranking
- query rewrite
- sufficiency verifier
- context packer
- answer generator
- citation verifier
- file-back proposal path

Query flow:

```text
query -> plan -> retrieve evidence/memory/wiki -> rerank -> pack context -> verify sufficiency -> answer -> verify citations -> optional file-back
```

Validation:

- answers cite source-backed evidence
- insufficient evidence leads to uncertainty or retrieval retry
- contradictory evidence is represented explicitly
- answer generation respects sensitivity policy
- retrieval quality is measured separately from generation quality

## Stage 9: Skill Runtime

Detailed plan: [stage-09-skill-runtime.md](stage-09-skill-runtime.md)

Purpose: execute controlled Python-based capabilities for deep search, file work, analysis, and actions.

Primary outputs:

- skill package format
- skill manifest schema enforcement
- skill registry
- sandbox runner
- dependency/environment setup
- input/output schema validation
- permission checks
- network/filesystem policy
- human approval queue
- skill audit trail
- generated artifact capture

Skill package:

```text
SKILL.md
manifest.yaml
input_schema.json
output_schema.json
main.py
tests/
fixtures/
```

Primary skill categories:

```text
deep_web_search
spreadsheet_analysis
word_report_generation
browser_research
data_cleanup
chart_generation
connector_action
wiki_file_back
```

Validation:

- skill cannot access undeclared files, network, secrets, or connectors
- skill outputs match declared schema
- outbound actions require approval by default
- generated artifacts are stored and audited
- skill failures are observable and recoverable

## Stage 10: Runtime-Agent Integration

Detailed plan: [stage-10-agent-integration.md](stage-10-agent-integration.md)

Purpose: combine retrieval, memory, and skills into an action-capable assistant.

Primary outputs:

- agent loop
- tool/skill planner
- context-aware skill selection
- action approval UX/API
- execution trace model
- task state persistence
- generated artifact filing
- memory/wiki file-back from useful outputs

Runtime loop:

```text
user request -> classify -> retrieve context -> plan -> call tools/skills -> observe -> verify -> answer/action proposal -> commit approved outputs
```

Validation:

- agent can answer without tools when tools are unnecessary
- agent can choose skills based on context and task
- untrusted retrieved content cannot directly instruct tools
- action traces are inspectable
- useful outputs can compound back into memory/wiki through patches

## Stage 11: External Connectors

Detailed plan: [stage-11-connectors.md](stage-11-connectors.md)

Purpose: expand ingestion beyond local files while preserving the same evidence contract.

Primary outputs:

- connector registry
- connector auth config
- cursor/checkpoint handling
- rate limiting
- retry/backoff
- webhook/poll scheduling
- per-source sensitivity policy
- replayable fixtures

Connector order:

```text
local folder
IMAP/email
Slack
web clipper / URL fetcher
Google Drive
calendar / CalDAV
```

Validation:

- every connector outputs `RawArtifact` and `NormalizedDoc`
- cursor replay is deterministic
- rate limits and failures do not corrupt state
- source ACL/sensitivity propagates into derived artifacts
- fixture replay works without live credentials

## Stage 12: API, UI, And Ops Surfaces

Detailed plan: [stage-12-api-ui-ops.md](stage-12-api-ui-ops.md)

Purpose: expose the engine to users and operators.

Primary outputs:

- FastAPI gateway
- source management API
- ingestion API
- query/chat API
- wiki browsing/patch API
- skill registry/run API
- approval inbox API
- jobs/ops API
- audit API
- minimal web UI

User surfaces:

```text
chat with citations
wiki browser
source setup
job dashboard
approval inbox
skill run history
audit/event view
```

Validation:

- API flows cover the main engine loop
- UI exposes enough state to debug ingestion and retrieval
- approvals are explicit and auditable
- failed jobs can be retried or inspected

## Stage 13: Evaluation Harness

Detailed plan: [stage-13-evaluation.md](stage-13-evaluation.md)

Purpose: make quality measurable and development agent-safe.

Primary outputs:

- golden workspace fixture
- expected claim sets
- expected retrieval sets
- expected contradiction cases
- expected wiki probes
- prompt-injection fixtures
- sensitivity leakage fixtures
- deletion fixtures
- benchmark runner
- eval reports

Evaluation dimensions:

```text
parse quality
claim extraction accuracy
source-span accuracy
retrieval relevance
context sufficiency
answer groundedness
citation correctness
contradiction detection
foresight usefulness
wiki compilation loss
skill safety
policy enforcement
cost and latency
```

Validation:

- CI can replay a small golden workspace
- eval results are comparable across model/router changes
- regression thresholds protect critical behavior
- LLM-as-judge outputs are sampled or calibrated against deterministic checks where possible

## Stage 14: Security, Privacy, And Hardening

Detailed plan: [stage-14-security-hardening.md](stage-14-security-hardening.md)

Purpose: make the engine trustworthy enough for real private workspaces.

Primary outputs:

- secret storage strategy
- encrypted connector credentials
- sensitivity propagation
- policy tests
- prompt-injection defenses
- taint tracking for untrusted content
- sandbox hardening
- backup/restore
- deletion/right-to-erasure flow
- audit integrity checks

Validation:

- restricted data cannot reach disallowed model providers
- prompt-injection fixtures cannot trigger unauthorized tools/actions
- secrets are not exposed to models or skill code unless explicitly allowed
- backup/restore is tested
- deletion removes or tombstones raw and derived artifacts according to policy

## Stage 15: Deployment And Operational Readiness

Detailed plan: [stage-15-deployment.md](stage-15-deployment.md)

Purpose: make the full system runnable and maintainable on a single node.

Primary outputs:

- Docker Compose stack
- service health checks
- migrations on startup or deploy
- local model profile
- cloud model profile
- GPU optional profile
- backup jobs
- restore documentation
- observability dashboard
- operator runbook

Services:

```text
gateway
ingest-worker
maintainer-worker
runtime-worker
postgres
object-store
model-runtime
web-ui
```

Validation:

- clean machine can start the stack
- health checks reflect real dependency health
- logs/traces connect jobs across services
- backup/restore succeeds on fixture workspace
- operator can inspect failed jobs, model spend, policy denials, and ingestion lag

## Cross-Stage Invariants

These must remain true throughout development:

- every artifact has an ID, schema version, provenance, and policy state
- every model call has task class, model, prompt version, sensitivity, token/cost metadata, and audit hash
- every derived claim can be traced to source spans
- every memory revision is append-only or explicitly superseding/retracting another object
- every wiki statement is supportable by claim IDs or marked as unresolved
- every skill run has manifest, inputs, outputs, permissions, logs, and audit events
- every outbound action requires explicit policy and usually human approval
- every package boundary is enforced by tests or import linting

## Detailed Plans

The per-stage detailed plans now exist under `docs/plans/`:

- [Stage 0: Repository And Architecture Guardrails](stage-00-repo-guardrails.md)
- [Stage 1: `metis-protocol`](stage-01-protocol.md)
- [Stage 2: `metis-core`](stage-02-core.md)
- [Stage 3: Local-First Ingestion Pipeline](stage-03-ingestion.md)
- [Stage 4: Model Router And Extraction Quality Loop](stage-04-model-router.md)
- [Stage 5: Memory Core](stage-05-memory-core.md)
- [Stage 6: Maintainer Worker](stage-06-maintainer.md)
- [Stage 7: Wiki Compiler And Human-Facing Knowledge](stage-07-wiki-compiler.md)
- [Stage 8: Retrieval And Query Runtime](stage-08-retrieval-runtime.md)
- [Stage 9: Skill Runtime](stage-09-skill-runtime.md)
- [Stage 10: Runtime-Agent Integration](stage-10-agent-integration.md)
- [Stage 11: External Connectors](stage-11-connectors.md)
- [Stage 12: API, UI, And Ops Surfaces](stage-12-api-ui-ops.md)
- [Stage 13: Evaluation Harness](stage-13-evaluation.md)
- [Stage 14: Security, Privacy, And Hardening](stage-14-security-hardening.md)
- [Stage 15: Deployment And Operational Readiness](stage-15-deployment.md)

Each detailed plan includes:

- objective
- package ownership
- concrete files/modules to create
- schemas/interfaces touched
- implementation steps
- tests and fixtures
- acceptance criteria
- risks and open questions

