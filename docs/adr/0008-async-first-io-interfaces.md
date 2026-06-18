# ADR 0008: Async-first I/O interfaces

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Metis services are I/O-bound: stores, object storage, the job queue, model
providers, and connectors all wait on network or disk. The shape of these
interfaces is fixed in `metis-protocol` (Stage 1) and is expensive to change once
implementations exist. Choosing sync-by-default now would force a painful
sync→async migration later.

## Decision

Protocol interfaces that touch I/O are **`async`**: stores (`ArtifactStore`,
`ClaimStore`, `MemoryStore`, ...), `ModelProvider`, the job queue, and the object
store. **Pure transforms stay synchronous**: mappers, policy decisions, and
context packing that perform no I/O. Tests use **pytest-asyncio** (`asyncio_mode =
auto`, ADR 0002).

## Consequences

- Services can exploit concurrency (e.g., fan-out retrieval) without re-shaping
  interfaces later.
- A clear sync/async split keeps CPU-bound pure logic easy to test and reason about.
- Implementations must use async-capable drivers (e.g., async DB/object-store
  clients) from Stage 2 onward.

## Alternatives considered

- **Sync-first with a later migration**: lower friction at Stage 0, but a costly,
  error-prone migration across every store and provider once code exists.
- **Sync core with async only at the edges**: pushes blocking calls into hot paths
  and complicates concurrency in the workers.
