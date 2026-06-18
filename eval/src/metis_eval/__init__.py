"""metis-eval: the evaluation harness.

Golden fixtures and quality comparisons that make model/pipeline changes measurable. Stage 5 seeds
the memory-vs-naive-RAG comparison (:mod:`metis_eval.memory`); Stage 13 adds the Metis-specific
benchmark — a deterministic, Docker-free golden-workspace replay across parse/claim/span/retrieval/
groundedness/contradiction/wiki-loss/skill-safety/policy dimensions, with regression thresholds, a
baseline-comparison report, and an LLM-judge calibrated against deterministic checks. The harness
may import any Metis package (a consumer, not a layer), so it is intentionally outside the
import-boundary contracts.
"""

from __future__ import annotations

from metis_eval.golden import GoldenWorkspace, golden_workspace
from metis_eval.judges import CalibrationReport, DeterministicJudge, calibrate
from metis_eval.report import BenchmarkReport, DimensionResult, Measurement
from metis_eval.runner import run_benchmark
from metis_eval.thresholds import BASELINE, THRESHOLDS, RegressionError, check_thresholds, gate

__version__ = "0.0.0"

__all__ = [
    "BASELINE",
    "THRESHOLDS",
    "BenchmarkReport",
    "CalibrationReport",
    "DeterministicJudge",
    "DimensionResult",
    "GoldenWorkspace",
    "Measurement",
    "RegressionError",
    "__version__",
    "calibrate",
    "check_thresholds",
    "gate",
    "golden_workspace",
    "run_benchmark",
]
