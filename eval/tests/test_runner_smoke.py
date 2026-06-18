"""The runner executes every dimension on the small golden workspace and produces a clean report."""

from __future__ import annotations

import json

from metis_eval import BASELINE, run_benchmark
from metis_eval.dimensions import DIMENSIONS
from metis_eval.report import BenchmarkReport, DimensionResult
from metis_eval.thresholds import THRESHOLDS


async def test_runner_executes_all_dimensions_and_passes() -> None:
    report = await run_benchmark()

    assert len(report.dimensions) == len(DIMENSIONS)
    assert set(report.scores()) == set(THRESHOLDS)  # every dimension scored against a threshold
    assert report.passed
    assert report.elapsed_ms >= 0.0
    # the headline safety + correctness dimensions are present and perfect on the golden set
    assert report.score("skill_safety") == 1.0
    assert report.score("groundedness") == 1.0
    assert report.score("policy_enforcement") == 1.0


async def test_report_compares_against_a_pinned_baseline() -> None:
    deltas = (await run_benchmark()).compare(BASELINE)
    assert {delta.name for delta in deltas} == set(BASELINE)
    # the deterministic engine reproduces the baseline exactly (no drift)
    assert all(abs(delta.delta) < 1e-9 for delta in deltas)


def test_report_serializes_for_archival() -> None:
    report = BenchmarkReport(
        dimensions=(DimensionResult("skill_safety", 1.0, True, 1.0, "contained"),),
        elapsed_ms=2.0,
    )
    encoded = json.loads(json.dumps(report.to_dict()))
    assert encoded["passed"] is True
    assert encoded["dimensions"][0]["name"] == "skill_safety"
