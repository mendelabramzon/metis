# ADR 0013: Model router placement, providers, and policy-bound routing

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 4 makes every LLM call swappable, policy-bound, measurable, and suitable for
structured extraction, replacing the temporary direct-model seam from Stage 3. The
router owns provider selection and policy enforcement; it must enforce provider
allowlists by sensitivity *before any prompt is built*, and CI must run without live
model calls. The plan also left the package placement open.

## Decision

**Placement: `metis_core.llm` (not `metis_core.models`).** The plan's `models/` path
collides with the Stage 2 ORM row package (also `metis_core/models/`), so the router
lives in `metis_core/llm/`. It stays in `metis-core` for now (shared infra next to the
Stage 2 policy helpers); extraction to a `metis-models` package is deferred until/if
the layer grows broad enough to warrant it.

**Default provider + model tiers (claude-api reference).** Anthropic Claude via the
async SDK, mapped from quality tiers: STANDARD -> `claude-sonnet-4-6`, FRONTIER ->
`claude-opus-4-8` (with `claude-fable-5` reserved for the hardest long-horizon work and
`claude-haiku-4-5` for cheap/fast). A single `task_class -> tier` table is the source of
truth shared by the router (provider selection) and the providers (model selection).
Anthropic calls use **adaptive thinking** (`thinking: {type: "adaptive"}`) +
`output_config.effort`, and **schema-bound structured output** (`output_config.format`).

**Policy enforced before prompt construction.** `MetisModelRouter.route()` takes only
task class + sensitivity (no prompt) and applies the allowlist: at/above the
`external_block_floor` (default RESTRICTED) external providers are skipped, so restricted
data routes to a local (non-external) provider regardless of tier. This mirrors the
Stage 2 `route_decision` helper. The `StubProvider` is the local, never-external provider
that serves every tier — restricted data and CI route here.

**No live calls in CI.** Providers take an injected client. `AnthropicProvider` is tested
against recorded/replayed responses (a fake client); the deterministic `StubProvider`
serves the router/call/structured/budget/audit unit tests and the extraction eval. There
are no network calls in the test suite.

**Structured output + bounded repair.** `structured.py` binds a protocol model's JSON
Schema to the request and validates the output into the protocol model; `repair.py`
retries schema-invalid outputs up to a bounded limit, while a hard `refusal` propagates
immediately (surfaced, not retried).

**Budget pre-flight.** Token counts are estimated with a heuristic (real `count_tokens`
is provider-specific and reconciled against the `ModelRun`'s actual usage); per-call token
and cost caps reject over-budget calls before generation, and cost is charged only for
external routing (local calls are free). Cost uses a per-model pricing table.

**Audited calls.** Every call emits a `model.call` audit event carrying the full
`ModelRun` (task class, provider, model, prompt version, sensitivity, token counts, cost,
cache hit, latency) plus a content hash that is stable across calls with identical inputs
(independent of the run id/timestamps). The append-only chain hash is added by the Stage 2
`AuditSink`.

## Consequences

- Restricted data provably never reaches a cloud provider; the check runs before any
  prompt bytes exist.
- Ingestion/maintainer/runtime share one `ModelCaller` entrypoint; Stage 3's deterministic
  baseline stays the default until a provider is configured, at which point the seam is the
  router.
- `metis-core` gains the `anthropic` runtime dependency. Provider-specific structured-output
  mechanics live in `structured.py`/the provider, so non-Anthropic providers degrade to
  repair without leaking the choice to callers.
- The extraction eval lives in `metis_core.llm.evaluation` as a seed; Stage 13 promotes it
  to the `eval/` workspace member.

## Alternatives considered

- **Router in `metis_core/models/`** (per the plan): collides with the ORM package; rejected
  in favor of `metis_core/llm/`.
- **Dedicated `metis-models` package now**: premature; revisit if the layer accretes
  provider-specific code (still `metis-protocol`-only deps).
- **LiteLLM for multi-provider routing**: Metis owns routing/policy; LiteLLM would only be an
  optional adapter detail, never the policy boundary.
- **Live calls in CI / golden text assertions**: non-deterministic and credential-bound; CI
  gates on schema-validity and recorded responses, with live runs reserved for the eval.
