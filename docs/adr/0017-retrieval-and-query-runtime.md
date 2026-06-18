# ADR 0017: Retrieval and query runtime

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 8 makes the system answer questions with sufficient, cited, policy-safe context, composing
retrieval, packing, a sufficiency check, generation, and citation verification. The plan warns
against retriever sprawl (hybrid + memory + wiki + graph) and reranker cost, and requires that
retrieval quality be measured separately from generation quality. This is the first
``metis-runtime`` stage; it answers but does not act (tools/agent loop are Stages 9-10).

## Decision

**The runtime composes the Stage 5 hybrid lookup; it does not re-implement hybrid search.**
``MemoryRetriever`` (the ``Retriever`` protocol impl) wraps ``MemoryIndexLookup`` (pgvector + FTS
+ reciprocal rank fusion). Per the plan's anti-overengineering guidance we **start with memory
only**; wiki/graph retrievers and cross-encoder reranking are deferred until the eval shows a gap.

**Sensitivity is enforced in retrieval.** The retriever drops any cell more restrictive than the
``QueryRequest.max_sensitivity`` ceiling before it can reach packing or an answer, so restricted
evidence is never surfaced to a lower-clearance requester. (Embedding routing for the query stays
local-first, as in Stage 5.)

**Self-RAG / CRAG flow, deterministic where it counts.** ``plan`` decides whether retrieval is
needed; ``BudgetedContextPacker`` assembles a token-bounded ``ContextBundle`` (cache-friendly
ordering — volatile context after the frozen instructions the answer step prepends);
``assess_sufficiency`` gates on whether any claim-cited evidence was retrieved. On a miss the
pipeline does one corrective retrieval (query rewrite + retry) and, failing that, returns an
**uncertainty answer rather than a fabrication**. The sufficiency check is deterministic so it
neither over-retries nor silently hallucinates.

**The answer is a runtime value, not a protocol artifact.** ``Answer`` carries the text plus the
exact claim/source-span citations. Generation has a deterministic extractive fallback (tests need
no model) and an optional ``query_answer`` LLM path; either way citations come from the retrieved
evidence, contradictions in the evidence are surfaced explicitly (never resolved away), and
``verify_citations`` flags any answer claim not present in the EvidenceSet. No new protocol schema
or event is introduced (a ``query.answered`` event waits for an event bus).

**File-back is always a proposal.** ``propose_fileback`` returns a claim-cited proposal for the
maintainer/approval flow to turn into a patch; the runtime never writes to the substrate. This is
a correctness/trust boundary.

**Retrieval quality is measured separately from generation.** ``metis_eval.retrieval`` scores span
recall@k purely from what the lookup returns — no answer generated — reusing the Stage 5 golden
corpus and loader; answer groundedness is the separate citation-verification gate.

## Consequences

- The five acceptance checks hold (against real Postgres): answers cite source-backed evidence;
  insufficient evidence yields uncertainty (not a guess); contradictory evidence is represented
  explicitly; restricted evidence is filtered for lower-clearance requesters; and retrieval recall
  is measured with no generation in the loop.
- The hybrid engine has one home (the Stage 5 core lookup); the runtime is a thin, policy-aware
  composition over it. Adding wiki/graph retrieval later is a new source fused in, not a rewrite.
- With the deterministic fallbacks, the whole pipeline runs in CI without a model; the LLM seams
  (``query_rewrite``/``query_answer``) slot in via the prompt registry when a caller is wired.

## Alternatives considered

- **A runtime ``hybrid.py`` re-implementing pgvector + FTS + RRF**: duplicates the Stage 5 core
  lookup; rejected in favor of composing it.
- **Shipping wiki + graph retrieval and a cross-encoder reranker now**: retriever sprawl and
  latency the plan warns against; deferred until the retrieval eval shows memory-only is
  insufficient.
- **An ``Answer`` protocol schema + ``query.answered`` event**: premature without an event bus or a
  cross-package consumer; the answer stays a runtime value until a surface (Stage 12) needs the
  contract.
- **LLM-judged sufficiency as the gate**: unreliable and costly as the only signal; a deterministic
  evidence-coverage check is the gate, with corrective retrieval as the escalation.
- **Direct file-back writes from useful answers**: violates the projection/trust boundary; file-back
  is always a proposal routed through approval.
