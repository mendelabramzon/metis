# Stage 2 Detailed Plan: `metis-core`

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 2. Builds on [stage-00-repo-guardrails.md](stage-00-repo-guardrails.md) (toolchain, ADRs) and [stage-01-protocol.md](stage-01-protocol.md) (schemas, interfaces, contract-test suites).

`metis-core` is the durable substrate. It is the first place protocol contracts get a real implementation: the database schema and migrations, object storage, the concrete stores, the append-only audit log, the job queue, and the deterministic policy decision helpers. Its job is to enforce the truth hierarchy and the cross-stage invariants at the storage boundary, so no later package can quietly violate them.

## Objective

- Implement the PostgreSQL schema and migrations for the protocol artifacts.
- Implement an object storage abstraction for immutable raw blobs and generated files.
- Implement the concrete stores (artifact, document, parsed/segment, claim/entity/event, memory, wiki patch) against the Stage 1 interfaces, and make them pass the Stage 1 contract suites against real Postgres.
- Implement the append-only, hash-chained audit log.
- Implement a Postgres-backed job queue behind a swappable interface.
- Implement deterministic policy decision helpers that need no LLM.
- Provide local development database setup and test infrastructure.

Non-goals (per `package-decomposition.md`): source connectors, chat/query planning, skill execution, background scheduling. Core stores and enforces; it does not produce evidence or act.

## Package Ownership

- Owns: `metis-core`.
- May depend on: `metis-protocol` only (import-linter enforced from Stage 0).
- Must not own: connectors, chat planning, skill logic, schedulers.
- Implements protocol interfaces: `ArtifactStore`, `DocumentStore`, `ClaimStore`, `MemoryStore`, `WikiStore`, `AuditSink`, and the infra `ObjectStore` and `JobQueue`. Also promotes the shared `BaseServiceSettings` referenced in Stage 0 into core.

## Key Decisions

| Decision | Choice | Rationale | Alternatives |
|---|---|---|---|
| Database | PostgreSQL 16+ | Canonical store for everything per engineering-refs; one system before specialization | — |
| DB access | SQLAlchemy 2.0 ORM, typed mappers | Type-safe, mature, pairs with Alembic | SQLAlchemy Core, raw asyncpg |
| Driver | asyncpg via SQLAlchemy async engine | Async-first interfaces (ADR `0008`) | psycopg3 async |
| Migrations | Alembic | Standard, reversible, autogenerate with review | hand-written SQL, sqitch |
| Vector column | pgvector extension, column reserved, index deferred | Avoid committing index params before retrieval stage | external vector DB (later) |
| Object storage | S3/MinIO via `boto3`, content-addressed (sha256) | Self-hostable, immutable blobs | filesystem (dev-only), `minio` SDK |
| Job queue | Postgres `FOR UPDATE SKIP LOCKED` behind `JobQueue` | No new infra in Phase 0; swappable later | Redis/RQ, Celery, arq |
| Audit | append-only table, hash chained per workspace | Tamper-evidence for Stage 14 integrity checks | plain append-only, external WORM |
| Test infra | testcontainers-python (ephemeral Postgres + MinIO) | Contract tests on real engines without polluting a dev DB | pytest-postgresql, shared dev DB |
| Multi-tenancy | row-level `workspace_id` on every table | Simple, indexable; revisit if isolation needs grow | schema-per-workspace |

## Concrete Files And Modules To Create

```text
packages/metis-core/src/metis_core/
  config.py                  # CoreSettings + BaseServiceSettings (promoted from Stage 0)
  db/
    engine.py                # async engine + sessionmaker
    session.py               # session/unit-of-work helpers
    base.py                  # DeclarativeBase, naming conventions
    types.py                 # typed-ID columns, JSONB, pgvector Vector, enum adapters
    mixins.py                # IdMixin, ProvenanceMixin, PolicyMixin, TimestampMixin, TombstoneMixin
  models/
    artifacts.py             # raw_artifacts, normalized_docs, parsed_docs, segments, source_spans
    claims.py                # claims, entities, events, extraction_batches
    memory.py                # memcells, memscenes, profiles, foresights, contradictions, memory_patches
    wiki.py                  # wiki_patches, wiki_pages
    audit.py                 # audit_events (hash-chained)
    jobs.py                  # jobs
  mappers.py                 # protocol model <-> ORM row translation
  objectstore/
    base.py                  # ObjectStore impl over S3/MinIO; content-addressed keys; immutability
  stores/
    artifact_store.py        # PostgresMinioArtifactStore
    document_store.py
    claim_store.py
    memory_store.py
    wiki_store.py
  audit/
    sink.py                  # append-only writer + hash chain
    verify.py                # verify_chain(workspace_id) integrity check
  jobs/
    queue.py                 # PostgresJobQueue: enqueue/lease/ack/nack/retry/backoff
    worker.py                # minimal Worker base used by Stage 0 service workers
  policy/
    decisions.py             # pure functions: route, skill_access, egress, sensitivity propagation
  tombstone.py               # deletion/tombstone propagation across derived artifacts
  migrations/
    env.py
    versions/0001_initial.py # all tables, indexes, pgvector + FTS, audit chain
  dev/
    docker-compose.dev.yml   # local Postgres + MinIO (or referenced from deploy/)
    seed.py reset.py
    testing.py               # testcontainers fixtures: ephemeral pg + minio

packages/metis-core/tests/
  test_migrations.py
  test_artifact_store_contract.py   # subclasses Stage 1 ArtifactStoreContract
  test_claim_store_contract.py
  test_memory_store_contract.py
  test_traceability.py
  test_idempotent_write.py
  test_immutability.py
  test_memory_supersession.py
  test_audit_chain.py
  test_job_queue_concurrency.py
  test_policy_decisions.py
  test_tombstone_propagation.py
packages/metis-core/fixtures/        # small golden artifact/claim set
```

## Schemas And Interfaces Touched

Implements the Stage 1 interfaces against real infrastructure:

- `ArtifactStore` → `PostgresMinioArtifactStore` (metadata in Postgres, blob in object store).
- `DocumentStore`, `ClaimStore`, `MemoryStore`, `WikiStore` → Postgres implementations.
- `AuditSink` → hash-chained append-only writer.
- `ObjectStore`, `JobQueue` → Postgres/MinIO implementations of the infra Protocols.

The ORM models mirror the protocol schemas via `mappers.py`; the protocol models remain the wire/contract truth and the ORM rows are storage detail. The truth hierarchy is encoded as foreign keys and constraints:

```text
RawArtifact -> SourceSpan -> Claim/Event/Entity -> MemCell/MemScene/Foresight -> WikiPatch/WikiPage
```

Storage-level enforcement of the cross-stage invariants:

- **Raw artifacts immutable**: no UPDATE path; uniqueness on `content_hash` for dedup; writes are insert-or-return-existing.
- **Derived artifacts versioned**: new versions insert new rows referencing prior versions, never overwrite.
- **Memory append-only**: `MemoryPatch` rows supersede/retract by reference; superseded rows stay queryable and auditable.
- **Wiki via patches**: writes go through `wiki_patches`; `wiki_pages` are derived.
- **Audit on writes**: every store write emits an `AuditEvent` through the sink.

## Implementation Steps

1. Stand up `db/` (async engine, session, declarative base, naming conventions) and `config.py` (`CoreSettings`, `BaseServiceSettings`).
2. Implement `db/types.py` and `db/mixins.py` so every table inherits id + provenance + policy + timestamps + tombstone columns consistently.
3. Define ORM models for the full truth hierarchy with foreign keys and constraints encoding immutability/versioning/append-only rules.
4. Write Alembic `0001_initial`: all tables; indexes (btree on `workspace_id`/`created_at`, GIN for FTS, reserved pgvector column with extension created); the audit chain column. Verify `upgrade head` from empty and `downgrade base`.
5. Implement `objectstore/base.py`: content-addressed keys (`sha256`), write-once semantics, get/put/exists; back it with MinIO/S3.
6. Implement `mappers.py` and each store in `stores/`, wiring blob storage for artifacts; subclass the Stage 1 contract suites and run them against testcontainers Postgres + MinIO.
7. Implement the audit sink with per-workspace hash chaining and `verify.py`; route all store writes through it.
8. Implement `jobs/queue.py` using `FOR UPDATE SKIP LOCKED` with lease/ack/nack/retry/backoff and a minimal `worker.py` base for the Stage 0 service workers.
9. Implement `policy/decisions.py` as pure, deterministic functions over the protocol policy vocabulary (no LLM, no I/O).
10. Implement `tombstone.py` deletion/erasure propagation across derived artifacts on a small fixture scope.
11. Provide `dev/` local stack (compose + seed/reset) and `dev/testing.py` testcontainers fixtures; wire them into CI.

## Tests And Fixtures

- **Migrations** (`test_migrations.py`): `alembic upgrade head` on an empty database succeeds; `downgrade base` is clean; re-`upgrade` is idempotent.
- **Contract suites** (headline): the Stage 1 `ArtifactStoreContract`, `ClaimStoreContract`, `MemoryStoreContract`, etc. run against real Postgres/MinIO via testcontainers and pass unchanged.
- **Traceability** (`test_traceability.py`): write `RawArtifact → SourceSpan → Claim`, then resolve any claim back to its source spans and raw artifact.
- **Idempotent write** (`test_idempotent_write.py`): writing the same raw bytes twice yields one logical artifact (dedup by `content_hash`).
- **Immutability** (`test_immutability.py`): attempts to mutate a raw artifact are rejected at the store layer.
- **Memory supersession** (`test_memory_supersession.py`): a superseding `MemoryPatch` hides the old cell from default queries but keeps it auditable; conflicting evidence does not silently merge.
- **Audit chain** (`test_audit_chain.py`): the per-workspace hash chain validates; tampering with a row is detected by `verify_chain`.
- **Job queue concurrency** (`test_job_queue_concurrency.py`): two concurrent workers never lease the same job (`SKIP LOCKED`); nack triggers backoff/retry; failures do not corrupt state.
- **Policy decisions** (`test_policy_decisions.py`): table-driven unit tests over sensitivity/task-class/tier combinations, fully deterministic, no LLM.
- **Tombstone propagation** (`test_tombstone_propagation.py`): tombstoning a raw artifact propagates to derived claims/memory per policy on a fixture.

Fixtures: a small golden set of artifacts, source spans, claims, and a memory cell in `fixtures/`, reused by the contract and traceability tests.

## Acceptance Criteria

Traces to the Stage 2 "Validation" list, plus enforcement and safety:

- Migrations apply from an empty database (and reverse cleanly).
- Stores pass the Stage 1 protocol contract tests against real Postgres + MinIO.
- Artifacts can be traced back to raw source spans.
- The deletion/tombstone flow works on a small fixture.
- Policy decisions are testable without an LLM.
- Every store write emits an audit event; the audit chain verifies and detects tampering.
- Raw immutability and memory append-only are enforced at the store layer, not by convention.
- The job queue is safe under concurrent workers.
- `make check` plus the testcontainers suite are green in CI.

## Risks And Open Questions

- **ORM vs Core**: SQLAlchemy ORM chosen for type-safety and Alembic integration; if specific write paths become hot, drop to Core selectively behind the same store interface.
- **`ObjectStore` / `JobQueue` placement**: this plan assumes they are protocol interfaces (Stage 1 open question). If Stage 1 instead keeps them in core, the import surface is unaffected but the interface lives here — reconcile before implementing `stores/`.
- **Audit chain ordering under concurrency**: a per-workspace hash chain needs a serialization point. Options: an advisory lock per workspace on append, or a monotonic per-workspace sequence with deferred chaining. Pick one in this stage's ADR; do not leave chaining racy.
- **pgvector index params**: deliberately deferred. Reserve the column and create the extension now; choose index type (HNSW vs IVFFlat) and dimensions in the retrieval stage when embedding models are fixed. Avoid committing to an embedding dimension prematurely.
- **Job queue scope**: Postgres `SKIP LOCKED` is right for Phase 0 but not infinite scale. The `JobQueue` interface keeps a later Redis/Celery swap cheap; scheduling (cron-like maintenance triggers) stays out of core (Stage 6).
- **Multi-tenancy**: row-level `workspace_id` is the Phase 0 model. If strong isolation is needed later, schema-per-workspace or RLS policies are the upgrade path; design indexes with `workspace_id` leading so that path stays open.
- **schema_version migration**: when protocol bumps a schema, decide whether to migrate rows or store version alongside and translate on read. Recommend translate-on-read via `mappers.py` for additive changes; reserve migrations for structural ones.
- **testcontainers in CI**: requires a Docker daemon in the runner (flagged in Stage 0). Confirm before this stage; otherwise fall back to a service-container Postgres + MinIO in the CI config.
