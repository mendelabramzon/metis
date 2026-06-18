"""The benchmark runner: load the golden workspace, run every dimension, produce a report.

Deterministic and Docker-free, so CI can replay the small golden workspace and diff the report
against thresholds within budget. Each dimension's score is stamped pass/fail against its threshold.
"""

from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter

from metis_eval.dimensions import DIMENSIONS
from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace, golden_workspace
from metis_eval.report import BenchmarkReport, DimensionResult
from metis_eval.thresholds import THRESHOLDS


async def run_benchmark(
    workspace: GoldenWorkspace | None = None,
    *,
    thresholds: Mapping[str, float] = THRESHOLDS,
) -> BenchmarkReport:
    """Run all dimensions on the golden workspace and return a thresholded report."""
    workspace = workspace if workspace is not None else golden_workspace()
    engine = GoldenEngine.load(workspace)

    start = perf_counter()
    results: list[DimensionResult] = []
    for evaluate in DIMENSIONS:
        measurement = await evaluate(workspace, engine)
        threshold = thresholds.get(measurement.name, 0.0)
        results.append(
            DimensionResult(
                name=measurement.name,
                score=measurement.score,
                passed=measurement.score >= threshold - 1e-9,
                threshold=threshold,
                detail=measurement.detail,
            )
        )
    elapsed_ms = (perf_counter() - start) * 1000.0
    return BenchmarkReport(dimensions=tuple(results), elapsed_ms=elapsed_ms)
