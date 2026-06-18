# Stage 5 Detailed Plan: Memory Core

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 5. Builds on Stages 0–4.

This stage turns extracted evidence into long-lived, queryable workspace memory: MemCells, MemScenes, profiles, and time-bounded foresights, with append-only revision and retrieval indexes. It adapts the EverMemOS lifecycle (MemCell/MemScene/Foresight, reconstructive recollection, background profile updates, sufficiency-driven retrieval) beyond chat to documents, files, and workspace events. Memory is interpreted from claims and source spans — it never invents facts that don't trace back to evidence.

## Objective

- Generate MemCells from claims/events, each traceable to source spans.
- Cluster MemCells into MemScenes with incrementally updatable summaries.
- Maintain Profile objects (stable workspace/user/company facts) with conflict tracking.
- Build time-bounded Foresight objects with validity windows and evidence.
- Implement the memory patch model with supersession/retraction (append-only).
- Build memory retrieval indexes and memory eval fixtures.

Non-goals: the background scheduler that runs these on a cadence (Stage 6), wiki projection (Stage 7), answer generation (Stage 8).

## Package Ownership

- Generation/consolidation logic: `metis-maintainer` (matches the `Consolidator` ownership in `package-decomposition.md`).
- Memory store + retrieval indexes: `metis-core` (durable substrate).
- Implements interfaces: `Consolidator` (and helpers the maintainer/Stage 6 jobs invoke).
- Uses the Stage 4 router for LLM-backed steps (`summarize_episode`, `consolidate_memory`, `build_foresight`).

Design note (open question below): the high-level event flow shows ingestion writing initial MemCells, while the decomposition assigns consolidation to the maintainer. This plan recommends **maintainer-time MemCell creation** driven by the `claims.extracted` event, keeping ingestion lean and dependencies clean.

## Concrete Files And Modules To Create

```text
packages/metis-maintainer/src/metis_maintainer/memory/
  memcell.py             # build MemCell from a claim/event cluster (LLM summarize_episode + evidence binding)
  scene.py               # MemScene clustering + incremental scene summaries (RAPTOR-style rollups)
  profile.py             # Profile builder with conflict tracking
  foresight.py           # Foresight builder: expected future state + validity window + evidence
  consolidate.py         # Consolidator impl: ExtractionBatch -> MemoryPatch
  supersession.py        # supersede/retract logic; conflict (non-merge) handling
  prompts.py             # task-class prompts (registry-managed via Stage 4)

packages/metis-core/src/metis_core/memory_index/
  embeddings.py          # versioned embedding generation, sensitivity-routed via the Stage 4 provider layer (restricted -> local); pgvector column wiring
  lookup.py              # memory index lookup primitive: MemCell/MemScene/Profile (vector + FTS). The Retriever protocol impl that composes it is runtime-owned (Stage 8)
  index_migrations/      # pgvector index creation (HNSW/IVFFlat) now that dims are fixed

eval/src/metis_eval/memory/   # memory-vs-naive-RAG comparison (golden questions live under eval/fixtures/, Stage 13)
packages/metis-maintainer/tests/
  test_memcell_traceability.py
  test_scene_incremental.py
  test_supersession.py
  test_conflict_no_merge.py
packages/metis-core/tests/
  test_memory_lookup.py
```

## Schemas And Interfaces Touched

- Produces/consumes `MemCell`, `MemScene`, `Profile`, `Foresight`, `Contradiction`, `MemoryPatch` (from `metis-protocol`); writes via the core `MemoryStore`.
- Reads `Claim`/`Event`/`Entity`/`SourceSpan`; every MemCell carries the claim and source-span references it was built from.
- Fixes the pgvector embedding dimension and index parameters deferred in Stage 2; embeddings are explicitly versioned.
- Emits events: `memcell.created`, `memscene.updated`, `profile.updated`, `foresight.created`.

## Implementation Steps

1. Implement `memcell.py`: cluster related claims/events, summarize via the router (`summarize_episode`), and bind every MemCell to its claim + source-span references.
2. Implement `scene.py`: cluster MemCells into MemScenes; generate scene summaries; support incremental update when new MemCells arrive (RAPTOR-style hierarchical rollup).
3. Implement `profile.py`: derive stable workspace/user/company facts; track conflicts explicitly rather than overwriting.
4. Implement `foresight.py`: produce expected-future-state objects with validity windows and supporting evidence.
5. Implement `consolidate.py` (the `Consolidator`) emitting `MemoryPatch`es, and `supersession.py` for supersede/retract — all append-only, conflicting evidence never silently merged.
6. Implement embedding generation (versioned; sensitivity-routed through the Stage 4 provider layer, restricted → local) and finalize the pgvector index in `metis-core`; build the memory index lookup primitive (vector + FTS with rank fusion). The runtime `Retriever` protocol impl that composes this lookup lands in Stage 8.
7. Build memory eval fixtures: golden long-horizon workspace questions comparing memory retrieval against naive chunk retrieval.

## Tests And Fixtures

- **Traceability** (`test_memcell_traceability.py`): every MemCell resolves to the claims and source spans it was built from.
- **Incremental scenes** (`test_scene_incremental.py`): adding a MemCell updates the relevant scene summary without a full recompute.
- **Supersession** (`test_supersession.py`): a stale fact is superseded; the prior version stays auditable.
- **Conflict handling** (`test_conflict_no_merge.py`): conflicting evidence produces a tracked conflict, not a silent merge.
- **Lookup correctness + headline metric** (`test_memory_lookup.py`; comparison in `eval/src/metis_eval/memory/`): the lookup primitive returns the right MemCells/MemScenes, and memory retrieval beats naive chunk retrieval on the golden workspace questions (the headline metric).

Fixtures: a golden workspace with documents/events that exercise episodes, scenes, profile conflicts, and a forward-looking foresight.

## Acceptance Criteria

Traces to the Stage 5 "Validation" list:

- MemCells are traceable to claims and source spans.
- Scenes can be incrementally updated.
- Stale memories can be superseded.
- Conflicting evidence does not silently merge.
- Memory retrieval beats naive chunk retrieval on golden workspace questions.

## Risks And Open Questions

- **Where MemCells are created**: recommend maintainer-time via `claims.extracted` (keeps ingestion lean, respects dependency rules) rather than ingestion-time as the decomposition sequence diagram suggests. Resolve in an ADR; if ingestion must create draft MemCells, the builder primitive moves to a shared location.
- **Embedding model + dimension lock-in**: choosing the embedding model fixes the pgvector dimension and index; version embeddings explicitly so a model change is a re-index, not a silent corruption.
- **Clustering quality**: MemScene clustering quality drives retrieval; start simple (embedding + claim-graph proximity) and measure before adopting heavier graph methods (HippoRAG/GraphRAG come later in Stage 8).
- **Profile conflict semantics**: deciding when two facts "conflict" vs "coexist" is subtle; keep conflicts explicit and defer resolution to the maintainer/contradiction detector (Stage 6).
- **Cost of consolidation**: LLM-backed summarization across many episodes is expensive; batch via the Stage 4 Batches path and gate on the eval harness before scaling.
- **Foresight validity**: expired foresights must be detectable; tie validity windows to the maintainer refresh jobs in Stage 6.
