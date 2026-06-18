# Stage 6 Detailed Plan: Maintainer Worker

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 6. Builds on Stages 0–5.

This stage runs background intelligence over memory and evidence: contradiction detection, episode revision, scene/profile refresh, foresight building, and wiki-patch proposal, all on a scheduler with a full audit trail. It operationalizes the reflection-as-scheduled-maintenance pattern (Generative Agents) and prepares the wiki-patch pipeline that Stage 7 deepens. Maintenance is idempotent and append-only — it proposes and supersedes, never silently overwrites.

## Objective

- Implement the maintainer job set: contradiction detection, episode revision, scene refresh, profile refresh, foresight building, wiki-patch compilation, wiki lint, claim-support validation, deletion validation.
- Implement a maintenance scheduler and a maintenance audit trail.
- Ensure all jobs are idempotent and produce auditable, append-only changes.

Non-goals: the deep wiki compile/evaluate/refine loop and commit flow (Stage 7 — this stage only proposes patches), retrieval/answering (Stage 8).

## Package Ownership

- Owns: `metis-maintainer` (+ `services/maintainer-worker` as the runner).
- May depend on: `metis-protocol`, `metis-core`; uses the Stage 4 router and the Stage 5 memory components.
- Implements interfaces: `ContradictionDetector`, `ForesightBuilder` (and the consolidation components from Stage 5).
- Must not own: connectors, UI/chat runtime, outbound actions.

## Concrete Files And Modules To Create

```text
packages/metis-maintainer/src/metis_maintainer/jobs/
  detect_contradictions.py   # ClaimContradictionDetector
  revise_episodes.py         # re-summarize MemCells when supporting claims change
  refresh_scenes.py          # incremental scene refresh
  refresh_profile.py         # profile rebuild with conflict tracking
  build_foresights.py        # TimelineForesightBuilder
  compile_wiki_patches.py    # propose WikiPatch from claims+memory (validated in Stage 7)
  lint_wiki.py               # structural/consistency lint of proposed patches
  validate_claim_support.py  # every derived statement still has claim support
  validate_deletions.py      # tombstone propagation correctness
packages/metis-maintainer/src/metis_maintainer/
  scheduler.py               # cadence + trigger model (event-driven + periodic), backoff
  registry.py                # job registry; each job declares inputs/idempotency key
  audit.py                   # maintenance audit trail helpers
services/maintainer-worker/  # leases jobs from the core JobQueue, runs the registry

packages/metis-maintainer/tests/
  test_contradiction_injection.py
  test_superseded_auditable.py
  test_wiki_patch_cites_claims.py
  test_deletion_propagation.py
  test_jobs_idempotent.py
```

## Schemas And Interfaces Touched

- Implements `ContradictionDetector`, `ForesightBuilder`; consumes/produces `Contradiction`, `MemoryPatch`, `Foresight`, `WikiPatch`.
- Reads claims/memory via core stores; writes patches and contradictions back through the append-only memory/wiki patch stores.
- Uses the core `JobQueue` (Stage 2) for scheduling and the `AuditSink` for the maintenance trail.
- Consumes events (`claims.extracted`, `memcell.created`) to trigger event-driven jobs; emits `contradiction.detected`, `wiki_patch.proposed`, etc.

## Implementation Steps

1. Implement `registry.py` and `scheduler.py`: jobs declare an idempotency key and trigger mode (event-driven and/or periodic); the scheduler enqueues into the core `JobQueue` with backoff.
2. Implement `detect_contradictions.py` (deterministic checks first, LLM judge second per the implementation biases) emitting `Contradiction` objects.
3. Implement `revise_episodes.py` and `refresh_scenes.py`/`refresh_profile.py` reusing the Stage 5 components; revisions supersede prior versions append-only.
4. Implement `build_foresights.py` and expire/refresh foresights past their validity window.
5. Implement `compile_wiki_patches.py` (propose only) plus `lint_wiki.py`, `validate_claim_support.py`, and `validate_deletions.py` — every proposed wiki statement must cite claim IDs.
6. Wire the maintenance audit trail; ensure every job run records inputs, outputs, and an audit event.
7. Stand up `services/maintainer-worker` to lease and run jobs from the registry.

## Tests And Fixtures

- **Contradiction injection** (`test_contradiction_injection.py`): a fixture with an injected contradiction is detected.
- **Superseded auditable** (`test_superseded_auditable.py`): revised/ superseded memories remain auditable.
- **Wiki patches cite claims** (`test_wiki_patch_cites_claims.py`): proposed patches reference claim IDs; unsupported statements are rejected.
- **Deletion propagation** (`test_deletion_propagation.py`): tombstone state propagates into derived artifacts.
- **Idempotency** (`test_jobs_idempotent.py`): re-running any job produces no duplicate effects.

Fixtures: a workspace seeded with a known contradiction, a stale fact, a deletion, and claims sufficient to compile a small wiki patch.

## Acceptance Criteria

Traces to the Stage 6 "Validation" list:

- The contradiction injection fixture is detected.
- Superseded memories remain auditable.
- Wiki patches cite claim IDs.
- Deletion/tombstone state propagates into derived artifacts.
- Maintainer jobs are idempotent.

## Risks And Open Questions

- **Deterministic-before-LLM discipline**: contradiction detection should run cheap deterministic checks first and reserve LLM judging for ambiguous cases; otherwise cost and false positives balloon.
- **Scheduling model**: event-driven vs periodic per job — pick per job in the registry; avoid a global tick that re-scans everything. The scheduler stays in the maintainer (out of `metis-core`).
- **Idempotency keys**: defining a correct key per job (so re-runs and retries don't duplicate patches) is the main correctness risk; test explicitly.
- **Patch volume**: wiki-patch proposal can flood the approval queue (Stage 7/12); rate-limit and dedupe proposals.
- **Ordering with concurrent ingestion**: maintenance over evidence that is still being written needs careful cursoring; lean on the append-only model and re-run rather than locking.
- **Foresight churn**: frequent foresight rebuilds are noisy; tie refresh to validity windows and material evidence changes only.
