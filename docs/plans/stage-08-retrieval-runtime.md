# Stage 8 Detailed Plan: Retrieval And Query Runtime

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 8. Builds on Stages 0–7.

This stage answers user questions with sufficient, cited, policy-safe context. It composes hybrid retrieval (lexical + vector with rank fusion), memory and wiki retrievers, optional graph/link traversal, reranking, query rewrite, a sufficiency verifier, a context packer, an answer generator, and a citation verifier — with a corrective fallback path. It applies Self-RAG-style sufficiency/critique and CRAG-style corrective retrieval, measuring retrieval quality separately from generation quality.

## Objective

- Implement a query API and the retrieval/answer flow `query → plan → retrieve → rerank → pack → verify sufficiency → answer → verify citations → optional file-back`.
- Implement hybrid, memory, and wiki retrievers plus optional graph/link traversal and reranking.
- Implement query rewrite, a sufficiency verifier, a budgeted context packer, an answer generator, and a citation verifier.
- Implement a file-back proposal path for useful answers.

Non-goals: tool/skill execution (Stage 9) and the full agent loop (Stage 10) — this stage answers; it does not act.

## Package Ownership

- Owns: `metis-runtime` (+ `services/runtime-worker`).
- May depend on: `metis-protocol`, `metis-core`, `metis-skills`; uses the Stage 4 router (`query_rewrite`, `query_answer`, `query_verify`).
- Implements interfaces: `Retriever` (`HybridRetriever`, `SceneRetriever`), `ContextPacker` (`BudgetedContextPacker`).

## Concrete Files And Modules To Create

```text
packages/metis-runtime/src/metis_runtime/query/
  api.py                 # QueryRequest -> answer pipeline entrypoint
  plan.py                # decide retrieval strategy + whether retrieval is needed (Self-RAG)
  rewrite.py             # query rewrite / HyDE-style expansion (optional)
  retrievers/
    hybrid.py            # pgvector + Postgres FTS with reciprocal rank fusion
    memory.py            # MemCell/MemScene/Profile Retriever impl; composes the Stage 5 memory index lookup
    wiki.py              # compiled-page retriever
    graph.py             # optional link/graph traversal (local-to-global)
  rerank.py              # reranking (cross-encoder/late-interaction optional)
  pack.py                # BudgetedContextPacker: ContextBundle within token budget
  sufficiency.py         # sufficiency verifier; trigger corrective retrieval (CRAG)
  answer.py              # answer generator over packed context
  cite_verify.py         # citation verifier: claims map to evidence
  fileback.py            # propose file-back (claim/memory/wiki) from useful answers

eval/src/metis_eval/retrieval/   # retrieval-quality vs answer-quality, measured separately
packages/metis-runtime/tests/
  test_citation_verifier.py
  test_sufficiency_retry.py
  test_contradiction_surfaced.py
  test_sensitivity_respected.py
  test_retrieval_metrics.py
```

## Schemas And Interfaces Touched

- Implements `Retriever` and `ContextPacker`; consumes `QueryRequest`, produces `EvidenceSet`, `ContextBundle`, and an answer artifact.
- Reads claims/memory/wiki via core stores; answers cite `SourceSpan`/claim IDs.
- Enforces `Sensitivity` policy in retrieval and answer generation (restricted evidence respects routing).
- Emits events: `query.answered`, `fileback.proposed`.

## Implementation Steps

1. Implement `api.py` and `plan.py`: classify the query and decide whether retrieval is needed and which retrievers to use (Self-RAG decision).
2. Implement `hybrid.py` (pgvector + FTS with reciprocal rank fusion), then `memory.py` and `wiki.py`; add optional `graph.py` traversal for multi-hop/global questions.
3. Implement `rewrite.py` (query rewrite / optional HyDE) and `rerank.py`.
4. Implement `pack.py`: budget-aware context assembly producing a `ContextBundle`, prompt-cache-friendly ordering (frozen instructions first).
5. Implement `sufficiency.py`: verify the packed context is sufficient; on insufficiency, trigger corrective retrieval (CRAG) or signal uncertainty rather than answering.
6. Implement `answer.py` and `cite_verify.py`: generate the answer and verify every claim maps to retrieved evidence; represent contradictions explicitly.
7. Implement `fileback.py`: propose claim/memory/wiki file-back from useful answers (patches, never direct writes).
8. Build the retrieval eval harness measuring retrieval relevance separately from answer groundedness.

## Tests And Fixtures

- **Citation verification** (`test_citation_verifier.py`): answers cite source-backed evidence; uncited claims are flagged.
- **Sufficiency retry** (`test_sufficiency_retry.py`): insufficient evidence triggers retrieval retry or an uncertainty response, not a confident hallucination.
- **Contradiction surfaced** (`test_contradiction_surfaced.py`): contradictory evidence is represented explicitly in the answer.
- **Sensitivity respected** (`test_sensitivity_respected.py`): restricted evidence is not surfaced to disallowed providers/answers.
- **Retrieval metrics** (`test_retrieval_metrics.py`): retrieval relevance is measured independently of generation.

Fixtures: golden workspace questions with known supporting spans, a multi-hop question, a contradictory-evidence question, and a sensitivity-restricted question.

## Acceptance Criteria

Traces to the Stage 8 "Validation" list:

- Answers cite source-backed evidence.
- Insufficient evidence leads to uncertainty or retrieval retry.
- Contradictory evidence is represented explicitly.
- Answer generation respects sensitivity policy.
- Retrieval quality is measured separately from generation quality.

## Risks And Open Questions

- **Retriever sprawl**: hybrid + memory + wiki + graph is a lot; start with hybrid + memory, add wiki/graph only when the eval shows a gap (RAG-vs-GraphRAG guidance: avoid graph overengineering).
- **Reranker cost/latency**: cross-encoder/late-interaction reranking is expensive; make it optional and benchmark against rank fusion alone (BEIR-style discipline).
- **Sufficiency verifier reliability**: a weak verifier either over-retries (cost) or under-retries (hallucination); calibrate against deterministic checks where possible.
- **Citation verification strictness**: too strict blocks valid answers, too loose permits unsupported claims; tune on the golden set.
- **Context-packing budget**: packing must respect token budgets and cache-friendly ordering; volatile per-query text goes after cached prefixes.
- **File-back safety**: file-back must always be a proposal/patch (never a direct write), gated by approval; this is a correctness and trust boundary.
