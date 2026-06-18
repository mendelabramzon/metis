# Stage 4 Detailed Plan: Model Router And Extraction Quality Loop

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 4. Builds on Stages 0–3.

This stage makes every LLM call swappable, policy-bound, measurable, and suitable for structured extraction. It replaces the temporary direct-model seam in Stage 3 with a routed, audited, budget-aware path that all later stages share. The router owns provider selection and policy enforcement; it does not own prompts' domain content (that lives with each caller via the prompt registry).

## Objective

- Implement model provider adapters behind the `ModelProvider` interface.
- Implement a `ModelRouter` that routes by task class, sensitivity, quality floor, latency, and budget, enforcing provider allowlists before any prompt is constructed.
- Implement a versioned prompt registry, structured-output validation, and a retry/repair loop.
- Log every model call with full metadata and an audit hash.
- Enforce budget and sensitivity policy.
- Build an extraction quality eval that compares model/provider choices.

Non-goals: memory consolidation logic (Stage 5), retrieval/answer generation (Stage 8), the agent loop (Stage 10).

## Package Ownership

- Owns: `metis-core` (shared infra used by ingestion, maintainer, runtime). The router sits next to the policy decision helpers from Stage 2.
- Implements interfaces: `ModelProvider`, `ModelRouter` (from `metis-protocol`).
- Open question (flagged below): extract to a dedicated `metis-models` package if `metis-core` grows too broad.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Default cloud provider | **Anthropic Claude** via the official `anthropic` SDK (async) | Latest, most capable; first-class structured output, caching, token counting |
| Default model tiers | `claude-opus-4-8` (high), `claude-sonnet-4-6` (balanced/bulk-quality), `claude-haiku-4-5` (cheap/fast), `claude-fable-5` (hardest long-horizon) | Map task classes → tiers by quality floor and cost |
| Other providers | OpenAI-compatible adapter; local via **vLLM**/**Ollama** (OpenAI-compatible) | Swappability + local fallback for restricted data |
| Multi-provider routing | Metis owns routing/policy; LiteLLM only as an optional adapter detail | Engineering-refs: "Metis should still own policy enforcement" |
| Reasoning control | adaptive thinking (`thinking: {type: "adaptive"}`) + `output_config.effort` per task class | Per-task depth without fixed token budgets |
| Structured output | `output_config.format` (json_schema) / `messages.parse()` with pydantic; strict tool use as fallback | Extraction batches validate against protocol schemas |
| Reliability | SDK auto-retry (429/5xx); `refusal` stop-reason handling; server-side `fallbacks` for `claude-fable-5` | Robust, policy-aware degradation |
| Cost levers | prompt caching for frozen prefixes; `count_tokens` pre-flight; Batches API for bulk non-latency work | Correctness first, then cost |

## Concrete Files And Modules To Create

```text
packages/metis-core/src/metis_core/models/
  provider.py            # ModelProvider impls: AnthropicProvider, OpenAICompatProvider, LocalProvider
  router.py              # ModelRouter: task_class + sensitivity + quality/latency/budget -> provider+model+params
  routing_config.py      # declarative route table (pydantic-settings); provider allowlists by sensitivity
  prompts/
    registry.py          # versioned prompt store: (task_class, version) -> template + schema ref
    templates/           # prompt templates per task class, content-hashed and versioned
  structured.py          # request structured output; validate against protocol schema; parse helpers
  repair.py              # retry/repair loop on schema-invalid or refusal outputs
  budget.py              # token/cost estimation (count_tokens) + budget enforcement
  call.py                # single entrypoint: route -> build prompt -> call -> validate -> audit
  audit_fields.py        # assemble the model-call audit record (+ hash)

eval/                    # workspace member (formalized in Stage 13); Stage 4 seeds extraction evals
  src/metis_eval/extraction/
    run.py                 # compare providers/models on a fixture set
    metrics.py             # claim/span accuracy, schema-validity rate, cost/latency

packages/metis-core/tests/
  test_router_policy.py
  test_provider_adapters.py     # against recorded/replayed responses
  test_structured_repair.py
  test_budget_enforcement.py
  test_model_audit.py
```

## Schemas And Interfaces Touched

- Implements `ModelProvider` and `ModelRouter`; consumes `ModelTaskClass`, `Sensitivity`, `ModelTier`, `PolicyDecision`.
- Reuses the Stage 2 policy helpers (`route_decision`) and `AuditSink`; every call emits an `AuditEvent` carrying `task_class`, `model_provider`, `model_name`, `prompt_version`, `sensitivity`, token counts, cost, `cache_hit`, `latency_ms`, provider `request_id`, and an audit hash (the observability fields from engineering-refs).
- Produces validated protocol objects (e.g., `ExtractionBatch`) via structured output bound to the protocol JSON Schema.

## Implementation Steps

1. Implement provider adapters behind `ModelProvider`; `AnthropicProvider` uses the async SDK with adaptive thinking + effort; `OpenAICompatProvider` covers OpenAI-style and vLLM/Ollama local endpoints.
2. Implement `routing_config.py` (declarative route table) and `router.py`; **enforce provider allowlists by sensitivity before constructing any prompt** — restricted data routes to local only.
3. Implement the versioned `prompt registry`; templates are content-hashed; `prompt_version` is logged on every call.
4. Implement `structured.py`: bind protocol JSON Schema to `output_config.format` (or strict tool use), parse to the protocol model; implement `repair.py` for schema-invalid outputs and `refusal` handling, with bounded retries.
5. Implement `budget.py`: pre-flight `count_tokens`, per-workspace/task budget caps, and rejection when over budget; record estimated vs actual.
6. Implement `call.py` as the single entrypoint used by ingestion (replacing the Stage 3 seam), maintainer, and runtime.
7. Wire prompt caching for frozen prefixes; record `cache_read_input_tokens` in audit.
8. Seed extraction evals in `eval/` comparing providers/models/effort on a fixture set; report accuracy, schema-validity, cost, latency.

## Tests And Fixtures

- **Routing policy** (`test_router_policy.py`): table-driven — restricted sensitivity never selects a cloud provider; quality floor/budget/latency select the expected tier; allowlist is checked before prompt build.
- **Provider adapters** (`test_provider_adapters.py`): against recorded/replayed responses (no live calls in CI); adaptive-thinking and structured-output request shapes are correct per provider.
- **Structured + repair** (`test_structured_repair.py`): malformed output triggers repair and ultimately validates against the protocol schema; a hard `refusal` is surfaced, not silently retried forever; bounded attempts.
- **Budget** (`test_budget_enforcement.py`): over-budget calls are rejected pre-flight; estimates recorded.
- **Audit** (`test_model_audit.py`): every call emits an audit event with the full field set and a stable hash; prompt + model versions are present.

Fixtures: recorded provider responses (success, malformed, refusal), a small extraction fixture reused from Stage 3, and a route-table fixture.

## Acceptance Criteria

Traces to the Stage 4 "Validation" list:

- Restricted artifacts never route to disallowed providers (enforced before prompt construction).
- Prompts and model versions are logged on every call.
- Malformed structured outputs are rejected or repaired.
- Local fallback works for restricted data.
- Extraction evals compare model/provider choices and produce a comparable report.
- Plus: budgets enforced pre-flight; `refusal` and rate-limit/5xx paths handled; cache hits recorded.

## Risks And Open Questions

- **Package placement**: the router lives in `metis-core` for now; if it accretes provider-specific code, extract `metis-models` (still `metis-protocol`-only deps). Decide via ADR before Stage 5 consumes it heavily.
- **Determinism in evals**: model outputs vary; gate CI on schema-validity and span/claim accuracy thresholds, not exact text. Use recorded responses for unit tests and live runs only in the eval harness.
- **Provider-specific structured-output mechanics**: keep the protocol-schema → provider-format translation in `structured.py` so non-Anthropic providers (which may lack equivalent guarantees) degrade to strict tool use or repair.
- **Budget accounting accuracy**: `count_tokens` is provider-specific; pre-flight estimates for local/OpenAI-compatible models differ from Anthropic — record estimate vs actual and reconcile.
- **Prompt-cache invalidation**: frozen prefixes must stay byte-stable; volatile fields (timestamps, per-doc text) go after the cache breakpoint, or cache hit-rate silently drops.
- **Batch vs interactive**: bulk extraction should prefer the Batches path (cheaper) while interactive query stays synchronous; the router must expose both without leaking the choice to callers.
- **Embeddings in the provider layer**: embeddings have no generative task class, but they are model calls that must honor the same provider allowlist — restricted data uses a local embedding model, never a cloud API. Expose embeddings via `ModelProvider` (or a sibling capability) so sensitivity routing is enforced centrally, not per caller (Stage 5 is the first consumer).
