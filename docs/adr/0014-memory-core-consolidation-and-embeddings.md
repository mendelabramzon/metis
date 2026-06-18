# ADR 0014: Memory core — consolidation placement, embedding lock-in, and hybrid lookup

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 5 turns extracted evidence into long-lived, queryable workspace memory (MemCells,
MemScenes, Profiles, Foresights) with append-only revision and retrieval indexes. The Stage 5
plan left several questions open: *where* MemCells are created (the high-level event flow shows
ingestion writing them, while the package decomposition assigns consolidation to the
maintainer); which embedding model — and therefore which pgvector dimension — to lock in (Stage 2
reserved the column dimensionless, ADR 0011); how conflicting facts should be handled; and where
the headline "memory beats naive RAG" comparison lives.

## Decision

**MemCells are created at maintainer time, one per `ExtractionBatch`.** The `Consolidator`
implementation lives in `metis-maintainer` (matching the decomposition), is driven by the
`claims.extracted` event (Stage 6 wires the schedule), and treats one parsed doc's extraction as
one episode. This keeps ingestion lean and dependencies inward (`maintainer -> core -> protocol`).
Each MemCell binds the exact claim refs and source-span refs it was interpreted from (the
traceability invariant) and gets a deterministic id derived from its input claim/event ids, so
re-consolidation is idempotent. Multi-cell-per-document clustering is deferred until the eval
justifies it; the `SceneBuilder` already clusters cells by shared-claim proximity.

**Embedding model and dimension are locked: bge-m3, 1024-dim, local-first.** `EMBEDDING_DIM` is
fixed in `metis_core.db.types`; every vector column is `vector(1024)`. Embeddings are a *derived
index detail*, not protocol truth, so they live in `metis_core.memory_index` (not on the protocol
`MemCell`) and are written by a `MemoryIndexer` *after* the object is stored, tagged with an
`embedding_version`. A model change is therefore an explicit re-index, never a silent
dimension/semantics mismatch. An `EmbeddingRouter` enforces *restricted → local* before any text
is sent (the embedding analogue of the model router's allowlist); the default local embedder is
Ollama bge-m3, with a deterministic `StubEmbedder` for CI and restricted fallback.

**pgvector HNSW + FTS GIN indexes are created in migration 0002.** They could not be declared in
Stage 2's `create_all` because HNSW requires a fixed dimension. The DDL is co-located with the
lookup code (`memory_index/index_migrations.py`) and applied by Alembic revision 0002; the FTS
expression is shared verbatim between the index and the query so the expression index is eligible.

**Lookup is hybrid vector + FTS fused with Reciprocal Rank Fusion.** The vector ranker is
restricted to the query's embedding version; superseded/retracted/tombstoned cells are excluded
(mirroring the store). This is a *primitive* — the policy-bound, query-rewriting `Retriever`
protocol implementation that composes it (plus wiki/graph retrieval) is runtime-owned in Stage 8.

**Conflicts are surfaced deterministically, never merged.** `ProfileBuilder` keys facts by claim
predicate; when one key carries distinct values it keeps every value as its own `conflicting=True`
fact and emits an explicit `Contradiction`. Deciding the winner (or whether two phrasings are the
same fact) is deferred to the Stage 6 contradiction detector. Scenes, by contrast, are
recomputable projections and evolve in place via incremental (RAPTOR-style) summary folding.

**The `eval/` workspace member is created now.** `metis_eval.memory` holds the golden workspace
fixture and the memory-vs-naive-RAG comparison (span coverage@k). The full benchmark harness is
Stage 13; this seeds the headline metric so model/pipeline changes are measurable today.

## Consequences

- The headline metric holds: a single consolidated MemCell covers a multi-fact question at k=1
  (coverage 1.00) where a single chunk covers a fraction (0.50), converging as k grows — verified
  deterministically (stub embedder) in CI and against real local bge-m3 embeddings.
- LLM-backed summarization goes through the Stage 4 `ModelCaller`; every builder also has a
  deterministic, evidence-only fallback, so unit tests run without a model and restricted data has
  a local path.
- Switching embedding models is a deliberate migration + re-index keyed on `embedding_version`,
  not a silent corruption; mixed-version vectors are simply not co-ranked.
- `OpenAICompatProvider` was hardened while exercising the local path: a runtime error body now
  raises a clean `ModelError` (not a `KeyError`), and non-JSON content flows to the repair loop
  instead of crashing. Note: `gemma4:e4b` via Ollama does plain generation fine but its
  *schema-constrained* decoding is memory-flaky on a single node ("failed to load model vocabulary
  required for format"); the locked dependency is the embedding model, not a local chat model.

## Alternatives considered

- **Ingestion-time MemCell creation** (per the high-level sequence diagram): would push
  consolidation/model concerns into ingestion and blur the dependency layering; rejected for
  maintainer-time creation. If draft MemCells ever must be created during ingestion, the builder
  primitive moves to a shared location.
- **A different embedding model (nomic-embed-text 768-dim, mxbai-embed-large 1024-dim)**: bge-m3 is
  already local, strong, and multilingual; the versioning scheme makes a later switch a re-index
  rather than a lock-in regret.
- **Embeddings on the protocol `MemCell`**: would make a re-buildable index detail part of the
  contract and couple schema versioning to model choice; kept in the core index layer instead.
- **Vector-only or FTS-only retrieval**: each misses cases the other catches (paraphrase vs. exact
  identifiers); RRF hybrid is more robust and is the measured baseline going into Stage 8.
- **Deferring the `eval/` package to Stage 13**: would leave the Stage 5 acceptance metric
  unmeasured; a minimal harness now is cheap and forward-compatible.
