# Stage 13 Detailed Plan: Evaluation Harness

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 13. Builds on Stages 0–12 (and seeded incrementally from Stage 4 onward).

This stage makes quality measurable and development agent-safe: a golden workspace fixture, expected claim/retrieval/contradiction/wiki-probe sets, prompt-injection and sensitivity-leakage and deletion fixtures, a benchmark runner, and eval reports. It draws on RAGAS/ARES for RAG metrics, BEIR for retrieval discipline, and AgentDojo for prompt-injection evals — but goes beyond generic RAG metrics to Metis-specific dimensions (claim/span accuracy, contradiction recall, wiki compilation loss, deletion correctness, sensitivity leakage).

## Objective

- Build a golden workspace fixture and the expected-output sets (claims, retrieval, contradictions, wiki probes).
- Build prompt-injection, sensitivity-leakage, and deletion fixtures.
- Implement a benchmark runner and eval reports.
- Make CI able to replay a small golden workspace with regression thresholds.

Non-goals: building the features under test (earlier stages) — this stage measures them. Security hardening itself is Stage 14 (this stage provides the adversarial fixtures it consumes).

## Package Ownership

- Owns: a top-level `eval/` workspace member (an application like `services/`, allowed to depend on `metis-runtime` for end-to-end runs; documented as an exception to the package DAG via import-linter).
- Consumes all engine packages through their public APIs; does not embed business logic.
- Extends the extraction/retrieval evals seeded in Stages 4 and 8.

## Concrete Files And Modules To Create

```text
eval/
  fixtures/
    golden_workspace/      # files, emails, chat logs, calendar items, web clips
    expected_claims/       # expected claim sets per document
    expected_retrieval/    # expected retrieval sets per query
    contradictions/        # injected-contradiction cases
    wiki_probes/           # diagnostic probes for compilation loss
    prompt_injection/      # adversarial documents (AgentDojo-style)
    sensitivity_leakage/   # restricted-data leakage cases
    deletion/              # right-to-erasure cases
  src/metis_eval/
    runner.py              # benchmark runner: orchestrate eval dimensions
    dimensions/            # one module per evaluation dimension
    judges.py              # LLM-as-judge wrappers, calibrated against deterministic checks
    report.py              # eval reports + comparison across model/router changes
    thresholds.py          # regression thresholds protecting critical behavior
  ci/
    small_golden.py        # CI-sized golden workspace replay

eval/tests/
  test_runner_smoke.py
  test_thresholds_enforced.py
```

## Schemas And Interfaces Touched

- Consumes engine outputs (claims, `EvidenceSet`, `Contradiction`, wiki pages, answers, skill results) via public APIs.
- Reuses audit/observability fields for cost/latency dimensions.
- No new protocol schemas; may define eval-only report models local to `metis-eval`.

## Implementation Steps

1. Build the golden workspace fixture and expected-output sets (claims, retrieval, contradictions, wiki probes).
2. Build the adversarial fixtures: prompt-injection documents, sensitivity-leakage cases, deletion/right-to-erasure cases.
3. Implement `runner.py` and the per-dimension modules covering: parse quality, claim-extraction accuracy, source-span accuracy, retrieval relevance, context sufficiency, answer groundedness, citation correctness, contradiction detection, foresight usefulness, wiki compilation loss, skill safety, policy enforcement, cost/latency.
4. Implement `judges.py` (LLM-as-judge) and calibrate/sample against deterministic checks where possible (ARES-style).
5. Implement `report.py` (comparable across model/router changes) and `thresholds.py` (regression gates).
6. Implement `ci/small_golden.py` so CI can replay a small golden workspace within time/cost budget.

## Tests And Fixtures

- **Runner smoke** (`test_runner_smoke.py`): the runner executes all dimensions on the small golden workspace and produces a report.
- **Thresholds enforced** (`test_thresholds_enforced.py`): a regression below threshold fails the eval (the CI gate).
- Fixtures: the golden workspace and all expected/adversarial sets above are themselves the primary deliverable consumed by every prior stage's quality tests.

## Acceptance Criteria

Traces to the Stage 13 "Validation" list:

- CI can replay a small golden workspace.
- Eval results are comparable across model/router changes.
- Regression thresholds protect critical behavior.
- LLM-as-judge outputs are sampled or calibrated against deterministic checks where possible.

## Risks And Open Questions

- **Import-boundary exception**: `eval/` depending on `metis-runtime` is an intentional exception to the DAG; document it in import-linter so it doesn't mask real violations.
- **LLM-judge reliability**: judges drift and disagree; calibrate against deterministic checks and sample human review; never gate solely on an unsampled judge.
- **Fixture realism vs determinism**: the golden workspace must be realistic enough to be meaningful yet deterministic enough for regression diffs; version it explicitly.
- **CI cost/time budget**: full evals are expensive; keep a small CI-sized golden workspace and run the full suite on demand/nightly.
- **Threshold calibration**: thresholds set too tight cause flaky failures, too loose let regressions through; baseline against recorded runs and revisit.
- **Provider variance**: model/provider changes shift absolute scores; report deltas against a pinned baseline so comparisons stay meaningful.
