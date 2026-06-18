# Stage 1 Detailed Plan: `metis-protocol`

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 1. Builds on [stage-00-repo-guardrails.md](stage-00-repo-guardrails.md) (toolchain and ADRs).

`metis-protocol` is the shared language of the system. It defines what messages mean: the schemas, the interfaces implementations must satisfy, the event envelope, the policy vocabulary, the provenance model, and the model task classes. It contains no I/O, no database code, no LLM calls, and no other `metis_*` import. Getting this layer right is what makes every later block swappable.

## Objective

- Define the core schemas, typed IDs and references, provenance model, and policy vocabulary.
- Define the protocol interfaces (Python `Protocol` types) that `metis-core` and later packages implement.
- Define the versioned event envelope and the event name catalog.
- Define the model task classes used for routing.
- Establish the schema versioning pattern and ship reusable contract-test helpers so implementers can prove conformance.
- Guarantee, by test and by import boundary, that protocol objects round-trip through JSON and depend on nothing internal.

Non-goals: any persistence, any concrete store, any model provider, any parsing. Interfaces are declared, not implemented.

## Package Ownership

- Owns: `metis-protocol` only.
- May depend on: third-party schema/runtime basics — pydantic v2, typing-extensions, a UUIDv7 helper. Nothing heavy, nothing with side effects.
- Must not own: database code, LLM calls, connector code, skill execution (per `package-decomposition.md`).
- Import-linter (from Stage 0) already enforces that `metis_protocol` imports no other `metis_*` package; this stage is the first real test of that contract.

## Concrete Files And Modules To Create

```text
packages/metis-protocol/src/metis_protocol/
  __init__.py            # curated public exports + __version__
  base.py                # ProtocolModel base: frozen, extra=forbid, json config
  versioning.py          # SchemaVersion, VersionedModel, schema registry, JSON Schema export
  ids.py                 # typed prefixed IDs (ArtifactId, ClaimId, ...), new_id()
  refs.py                # typed references (SourceSpanRef, ClaimRef, WorkspaceRef, ...)
  enums.py               # shared enums (Sensitivity, ModelTier, JobState, ArtifactKind, ...)
  provenance.py          # Provenance, Derivation, Attribution, ModelRun (W3C PROV-inspired)
  policy.py              # PolicyTags, PolicyState, PermissionScope, PolicyDecision
  tasks.py               # ModelTaskClass enum (the 14 task classes)
  errors.py              # typed protocol error hierarchy

  artifacts.py           # RawArtifact, NormalizedDoc, ParsedDoc, Segment, SourceSpan
  claims.py              # Claim, Entity, Event, ExtractionBatch
  memory.py              # MemCell, MemScene, Profile, Foresight, Contradiction, MemoryPatch
  wiki.py                # WikiPatch, WikiPage
  query.py               # QueryRequest, EvidenceSet, ContextBundle
  skills.py              # SkillManifest, SkillInput, SkillResult
  audit.py               # AuditEvent
  events.py              # EventEnvelope, EventName, payload registry

  interfaces/
    __init__.py
    connectors.py        # Connector, Parser, Extractor
    processing.py        # Consolidator, ContradictionDetector, ForesightBuilder
    stores.py            # ArtifactStore, DocumentStore, ClaimStore, MemoryStore, WikiStore
    infra.py             # ObjectStore, JobQueue  (see open questions)
    audit.py             # AuditSink
    models.py            # ModelProvider, ModelRouter
    retrieval.py         # Retriever, ContextPacker
    skills.py            # Skill, SkillRunner

  contract_tests/
    __init__.py
    artifact_store.py    # abstract pytest suite: ArtifactStoreContract
    claim_store.py       # ClaimStoreContract
    memory_store.py      # MemoryStoreContract
    ...                  # one per store/interface that has invariants
    in_memory/           # reference in-memory fakes used to self-test the suites

packages/metis-protocol/tests/
  test_json_roundtrip.py
  test_invariants.py     # every artifact carries id + schema_version + provenance + policy
  test_event_envelope.py
  test_schema_snapshots.py
  test_contract_helpers.py
packages/metis-protocol/fixtures/   # one example JSON per schema
schemas/                            # generated JSON Schema exports (committed)
```

## Schemas And Interfaces Touched

This is where all of them are born. The cross-stage invariants require that **every artifact has an ID, schema version, provenance, and policy state** — enforced by a shared base rather than repeated by hand.

Base and versioning:

```python
# base.py
class ProtocolModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", ser_json_bytes="base64")

# versioning.py
class VersionedModel(ProtocolModel):
    schema_version: SchemaVersion          # e.g. "1.0"; additive bumps are backward-compatible

class Artifact(VersionedModel):
    id: ArtifactId
    provenance: Provenance
    policy: PolicyState
    created_at: datetime
    tombstoned_at: datetime | None = None
```

Representative schema stubs (illustrative, not exhaustive):

```python
# artifacts.py
class SourceSpan(VersionedModel):
    id: SourceSpanId
    artifact_id: ArtifactId
    doc_id: DocId | None
    char_start: int
    char_end: int
    page: int | None = None
    locator: str | None = None   # connector-native locator (e.g. xpath, cell ref)

class RawArtifact(Artifact):
    kind: ArtifactKind
    content_hash: str            # sha256; immutability + dedup key
    media_type: str
    byte_size: int
    storage_ref: str             # object-store key, resolved by core

# claims.py
class Claim(Artifact):
    text: str
    predicate: str | None
    subject_ref: EntityRef | None
    object_ref: EntityRef | None
    source_spans: tuple[SourceSpanRef, ...]   # non-empty: every claim cites evidence
    confidence: float

# events.py
class EventEnvelope(VersionedModel):
    event_id: EventId
    event_name: EventName
    event_version: int
    occurred_at: datetime
    workspace_id: WorkspaceId
    trace_id: str
    payload_schema_version: SchemaVersion
    payload: Mapping[str, object]
```

Representative interface (async-first for I/O, per Stage 0 ADR `0008`):

```python
# interfaces/stores.py
@runtime_checkable
class ClaimStore(Protocol):
    async def write(self, batch: ExtractionBatch) -> ClaimWriteResult: ...
    async def query(self, filter: ClaimFilter) -> Sequence[Claim]: ...
    async def get(self, claim_id: ClaimId) -> Claim | None: ...
```

Full surface delivered this stage:

- Schemas: `RawArtifact`, `NormalizedDoc`, `ParsedDoc`, `Segment`, `SourceSpan`, `Claim`, `Entity`, `Event`, `ExtractionBatch`, `MemCell`, `MemScene`, `Profile`, `Foresight`, `Contradiction`, `MemoryPatch`, `WikiPatch`, `WikiPage`, `QueryRequest`, `EvidenceSet`, `ContextBundle`, `SkillManifest`, `SkillInput`, `SkillResult`, `AuditEvent`, `EventEnvelope`.
- Vocabularies: `Sensitivity`, `ModelTier`, `PolicyState`, `PermissionScope`, `ModelTaskClass`, `EventName`, `ArtifactKind`, `JobState`.
- Provenance: `Provenance`, `Derivation`, `Attribution`, `ModelRun`.
- Interfaces: `Connector`, `Parser`, `Extractor`, `Consolidator`, `ContradictionDetector`, `ForesightBuilder`, `ArtifactStore`, `DocumentStore`, `ClaimStore`, `MemoryStore`, `WikiStore`, `AuditSink`, `ModelProvider`, `ModelRouter`, `Retriever`, `ContextPacker`, `Skill`, `SkillRunner`, plus infra `ObjectStore` and `JobQueue`.

## Implementation Steps

1. Implement `base.py` (frozen, extra-forbid model) and `versioning.py` (`SchemaVersion`, `VersionedModel`, registry, JSON Schema export helper).
2. Implement `ids.py` (prefixed UUIDv7 typed IDs with validation and `new_id(prefix)`), `refs.py`, and shared `enums.py`.
3. Implement `provenance.py` and `policy.py` — these are embedded by nearly every schema, so land them before the schema layer.
4. Implement the artifact layer (`artifacts.py`), then claims/entities/events (`claims.py`), enforcing non-empty `source_spans` on `Claim`.
5. Implement memory (`memory.py`), wiki (`wiki.py`), query (`query.py`), skills (`skills.py`), audit (`audit.py`).
6. Implement `tasks.py` (the 14 task classes) and `events.py` (envelope + `EventName` catalog + payload-version registry).
7. Implement the `interfaces/` Protocols; mark I/O interfaces async and pure transforms sync per ADR `0008`; add `@runtime_checkable` where structural checks are useful.
8. Implement `contract_tests/` abstract suites plus in-memory reference fakes, and self-test the suites against those fakes.
9. Export JSON Schema for all schemas to `schemas/` and wire the schema-snapshot test.
10. Write example fixtures (one JSON per schema) used by round-trip tests and by downstream stages.
11. Tag the protocol surface `v1` and add an ADR documenting the versioning and async-interface decisions.

## Tests And Fixtures

- **JSON round-trip** (`test_json_roundtrip.py`): for every schema, `model_validate_json(model_dump_json(x)) == x`; property-based generation with hypothesis to cover edge cases, plus the committed fixtures as concrete anchors.
- **Structural invariants** (`test_invariants.py`): introspect all `Artifact` subclasses and assert each carries `id`, `schema_version`, `provenance`, and `policy`; assert `Claim.source_spans` is non-empty by construction.
- **Event envelope versioning** (`test_event_envelope.py`): every `EventName` has a registered payload schema and `event_version`; unknown event names are rejected.
- **Schema snapshots** (`test_schema_snapshots.py`): exported JSON Schema matches the committed `schemas/` snapshots; a mismatch forces an intentional version bump rather than a silent breaking change.
- **Contract helpers** (`test_contract_helpers.py`): the in-memory fakes pass the abstract store suites, proving the suites are usable and correct before `metis-core` consumes them in Stage 2.
- **No internal dependency**: covered by the Stage 0 import-linter contract; add an explicit assertion test that `metis_protocol` imports no `metis_*` package as a fast local signal.

Fixtures: `fixtures/<schema>.json` — minimal valid examples per schema, doubling as documentation and as input for Stage 2/3 store and ingestion tests.

## Acceptance Criteria

Traces to the Stage 1 "Validation" list, plus contract-readiness:

- Schemas round-trip through JSON with equality preserved.
- Event envelopes are versioned and every event name resolves to a versioned payload schema.
- Every artifact can carry provenance and policy, verified structurally across all schema classes.
- No protocol object depends on storage implementation details (import-linter + assertion test).
- mypy strict is clean across the package; `@runtime_checkable` Protocols behave under isinstance where declared.
- The contract-test suites are importable and pass against the in-memory fakes, ready for `metis-core`.
- JSON Schema exports are committed and snapshot-tested.

## Risks And Open Questions

- **Premature lock-in**: freezing 24+ schemas before any ingestion exists risks churn. Mitigation: additive-only versioning, `extra="forbid"` to surface drift loudly, and a willingness to bump `schema_version` rather than mutate v1 in place. Treat v1 as "stable but expected to grow."
- **`ObjectStore` and `JobQueue` placement**: these are infra contracts that `metis-core` implements and `metis-protocol` does not strictly need for its own schemas. Recommendation: define them in `metis-protocol/interfaces/infra.py` so they stay swappable, even though they are infra-flavored. If that feels wrong, they move to `metis-core` and Stage 2 owns them — decide in this stage's ADR.
- **`Profile` schema**: referenced by Stage 5 but not in the original Stage 1 core schema list. Included here so memory has a stable profile type to target; confirm field set is acceptable as a v1 draft.
- **Async vs sync interfaces**: locked to async-first for I/O per ADR `0008`. Risk is forcing async on a future trivial in-process implementation; acceptable, since fakes can be trivially async.
- **Schema library**: pydantic v2 chosen for ergonomics and JSON Schema export. If serialization throughput becomes a bottleneck later, `msgspec` is a candidate, but only behind the same `ProtocolModel` surface.
- **ID scheme**: prefixed UUIDv7 (ADR `0007`). Open: exact prefix table and whether to expose a sortable external form (e.g., base32) for logs — settle the prefix registry in `ids.py`.
- **Event transport vs definition**: this stage defines the envelope, not how it is published. Keep the envelope serializer-agnostic; the transport (in Postgres `LISTEN/NOTIFY`, queue table, or external bus) is a Stage 2+ decision.
