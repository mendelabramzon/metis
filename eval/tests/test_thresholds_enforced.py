"""A regression below threshold fails the gate; the golden report passes; the judge is checked."""

from __future__ import annotations

import pytest

from metis_eval import RegressionError, check_thresholds, gate, run_benchmark
from metis_eval.judges import DeterministicJudge, calibrate
from metis_eval.report import BenchmarkReport, DimensionResult
from metis_protocol import ClaimId, ClaimRef, QueryId, new_id
from metis_runtime.query import Answer


async def test_golden_report_passes_the_gate() -> None:
    report = await run_benchmark()
    gate(report)  # does not raise
    assert check_thresholds(report) == []


def test_regression_below_threshold_is_caught() -> None:
    degraded = BenchmarkReport(
        dimensions=(DimensionResult("skill_safety", 0.0, False, 1.0, "a tool fired"),),
        elapsed_ms=1.0,
    )
    violations = check_thresholds(degraded, {"skill_safety": 1.0})
    assert [violation.name for violation in violations] == ["skill_safety"]

    with pytest.raises(RegressionError):
        gate(degraded, {"skill_safety": 1.0})


def test_judge_is_calibrated_against_deterministic_checks() -> None:
    query_id = new_id(QueryId)
    claim_id = new_id(ClaimId)
    grounded = Answer(
        query_id=query_id, text="ok", claims=(ClaimRef(claim_id=claim_id),), sufficient=True
    )
    insufficient = Answer(query_id=query_id, text="no", sufficient=False)
    # (answer, retrieved-evidence ids, ground-truth label)
    cases = [
        (grounded, {str(claim_id)}, True),  # cited claim is in evidence -> grounded
        (grounded, set(), False),  # cited claim absent from evidence -> not grounded
        (insufficient, set(), False),  # insufficient answer -> not grounded
    ]

    report = calibrate(DeterministicJudge(), cases)
    assert report.agreement == 1.0  # the anchor agrees with its own labels
