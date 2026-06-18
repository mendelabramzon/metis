# ADR 0010: Protocol schema versioning and interface placement

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 1 freezes 25+ schemas and ~24 interfaces in `metis-protocol` before any
ingestion, storage, or model code exists. Every later block is swapped behind
these contracts, so we need a versioning discipline that tolerates growth without
silent breakage, and we need to settle three questions the plan left open: the
schema-version pattern, where infra interfaces (`ObjectStore`, `JobQueue`) live,
and confirmation of the async/sync split for interfaces.

## Decision

**Schema versioning is additive and snapshot-guarded.**

- Every model carries a ``schema_version`` (``"<major>.<minor>"``); the v1 surface
  is ``"1.0"``. Backward-compatible additions keep the version; breaking changes
  bump it. We supersede rather than mutate.
- ``ProtocolModel`` is ``frozen=True, extra="forbid"`` so drift fails loudly at
  the boundary instead of being silently dropped.
- JSON Schema for every registered schema is exported to
  ``packages/metis-protocol/schemas/`` and snapshot-tested; a diff forces an
  intentional regeneration (``scripts/regenerate.py``). Committed example fixtures
  under ``packages/metis-protocol/fixtures/`` anchor round-trip tests and seed
  downstream stages. (Both directories live inside the package, not at the repo
  root, so the package stays self-contained and its tests are hermetic.)
- IDs are typed, prefixed UUIDv7 strings (ADR 0007); the prefix registry lives in
  ``ids.py``.

**Infra interfaces live in ``metis-protocol``.** ``ObjectStore`` and ``JobQueue``
are defined in ``interfaces/infra.py`` even though `metis-core` implements them
and the protocol's own schemas do not need them. Keeping them here keeps storage
and queueing swappable behind the protocol, consistent with every other
interface. The ``Job`` schema they depend on lives in ``events.py`` (operational
messaging) and is registered like other schemas.

**Interfaces are async-first for I/O, sync for pure transforms** (confirming
ADR 0008). Async: stores, `ObjectStore`, `JobQueue`, `AuditSink`, `ModelProvider`/
`ModelRouter.generate`, `Connector.discover`/`fetch`, `Extractor`, the
maintenance processors, `Retriever`, `Skill`/`SkillRunner`. Sync: `Connector.normalize`,
`Parser`, `ContextPacker.pack`, `ModelRouter.route`, and the policy helpers. I/O
interfaces are marked ``@runtime_checkable`` so structural conformance can be
asserted.

## Consequences

- Downstream stages target a stable but growing v1; the snapshot test is the
  trip-wire against accidental breakage.
- A reusable contract-test suite (``metis_protocol.contract_tests``, behind the
  ``contract-tests`` extra) lets any store implementation prove conformance; the
  in-memory fakes self-test the suites.
- `metis-protocol` gains one runtime dependency (pydantic v2) and an optional
  pytest extra; it still imports no other `metis_*` package (enforced by
  import-linter plus a local AST test).
- The envelope's id field is ``envelope_id``/``EnvelopeId``; the domain occurrence
  schema keeps ``EventId``, resolving the plan snippet's name clash.

## Alternatives considered

- **`ObjectStore`/`JobQueue` in `metis-core`**: tighter cohesion with their
  implementations, but it would make queueing/storage non-swappable behind the
  protocol and split the interface surface across two packages. Rejected.
- **`msgspec` instead of pydantic v2**: faster serialization, but pydantic's
  validation ergonomics and JSON Schema export win at this stage; revisit only
  behind the same ``ProtocolModel`` surface if throughput demands it.
- **Mutable, in-place schema edits**: simpler short term, but destroys the
  provenance and reproducibility guarantees. Rejected in favor of additive
  versioning.
