# ADR 0022: Evaluation harness — a deterministic golden benchmark, thresholds, and judge calibration

- Status: Accepted
- Date: 2026-06-19
- Deciders: Metis maintainers

## Context

Stage 13 makes quality measurable and development agent-safe: a golden workspace, expected
claim/retrieval/contradiction/wiki-probe sets, adversarial (prompt-injection, sensitivity-leakage,
deletion) cases, a benchmark runner, regression thresholds, and CI replay. It draws on RAGAS/ARES
(RAG metrics + judge calibration), BEIR (retrieval discipline), and AgentDojo (prompt-injection
evals), but adds Metis-specific dimensions (claim/span accuracy, contradiction recall, wiki
compilation loss, deletion correctness, sensitivity leakage). The constraint: CI must replay a small
golden workspace within a time/cost budget, and results must stay comparable across model/router
changes.

## Decision

**The CI benchmark is deterministic and Docker-free; the deep evals stay Postgres-backed.** The
Stage 5/8 memory and retrieval evals keep using testcontainers Postgres + pgvector for a real
hybrid-retrieval read. Stage 13 adds a *small golden-workspace replay* that runs the real Stage 3
``BaselineExtractor`` and the real Stage 10 ``AgentLoop`` over an in-memory engine — so claims,
spans, and the prompt-injection containment are genuine — with deterministic lexical retrieval. This
is what lets CI diff a regression report in milliseconds without infra, while the heavier suites run
on demand/nightly.

**The golden workspace is code-pinned truth over inspectable files.** Document *text* lives in
``eval/fixtures/`` (versioned, human-readable); per-document metadata (sensitivity, deletion,
injection) and the expected claim/retrieval/contradiction/wiki-probe sets live in ``golden.py`` so
the golden truth is deterministic and diffable. A single fixture drives every dimension.

**One dimension per quality/safety axis, each a 0–1 score stamped against a threshold.** Nine
dimensions ship: parse quality, claim extraction, span accuracy, retrieval relevance, answer
groundedness (with citation correctness), contradiction recall, wiki compilation loss, skill safety
(AgentDojo-style injection containment), and policy enforcement (sensitivity leakage + deletion). A
dimension returns a ``Measurement``; the runner stamps pass/fail against ``THRESHOLDS``. Safety and
correctness dimensions are held at 1.0 (no regression tolerated); quality dimensions get slack.

**Reports compare against a pinned baseline, not raw absolutes.** ``BenchmarkReport.compare`` yields
per-dimension deltas vs a pinned ``BASELINE``, so a model/router swap is read as movement against a
fixed reference rather than a number that drifts with the provider — the comparability the plan
requires. Reports serialize to JSON for CI artifacts.

**The LLM judge is calibrated against deterministic checks; it is never trusted unsampled.** A
``GroundednessJudge`` decides whether an answer is grounded; the *deterministic* judge (every cited
claim is in the retrieved evidence and the answer is sufficient) is the calibration anchor.
``calibrate`` measures a judge's agreement with the deterministic ground-truth labels, so a real LLM
judge must clear a calibration bar before it can gate anything (ARES-style).

**``metis-eval`` is a consumer outside the boundary contracts.** It depends inward on every engine
package (now including ``metis-ingestion`` and ``metis-runtime``) through public APIs. It is not a
root package in import-linter, so it is already exempt from the DAG layering — the intended exception
the plan calls for, recorded in the package docstring.

## Consequences

- The four acceptance checks hold with no Docker: ``make eval`` (and the test suite) replays the
  small golden workspace; results compare against a pinned baseline; thresholds fail a regression
  (the headline safety/correctness dimensions sit at 1.0); and the judge is calibrated against the
  deterministic checks. ``python -m metis_eval.ci.small_golden`` is the budgeted CI entrypoint.
- The deterministic engine necessarily approximates retrieval (lexical, not pgvector), so absolute
  scores are a floor, not the production number — the Postgres-backed evals remain the real-quality
  read. Foresight usefulness is deferred (its substrate is heavier than the small replay warrants).
- New eval deps: ``metis-ingestion`` + ``metis-runtime``. No protocol changes; report/threshold
  models are eval-local.

## Alternatives considered

- **A Postgres/pgvector golden replay in CI for every dimension**: most faithful but slow and infra-
  bound; the deterministic in-memory replay keeps the CI gate fast while reusing the *real* extractor
  and agent for the dimensions that matter most (claims, spans, injection containment).
- **On-disk JSON for the expected sets**: rejected for code-pinned expectations — code is more
  diffable, type-checked, and avoids a second source of truth drifting from the fixtures.
- **Gating CI on an unsampled LLM judge**: explicitly rejected — judges drift and disagree; the
  deterministic anchor + calibration is the guardrail, and only a calibrated judge may gate.
- **Reporting raw absolute scores**: rejected — provider variance makes absolutes incomparable;
  deltas against a pinned baseline keep model/router comparisons meaningful.
- **One mega-dimension**: rejected — one module per axis keeps each metric independently thresholded
  and a regression precisely attributable.
