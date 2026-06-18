"""Eval report primitives: a per-dimension measurement, the report, and baseline comparison.

A dimension produces a :class:`Measurement` (a 0-1 score plus a human note); the runner stamps it
with its threshold into a :class:`DimensionResult`. A :class:`BenchmarkReport` aggregates them and
can ``compare`` against a pinned baseline — so a model/router change is read as *deltas*, not raw
scores that drift with the provider. These are eval-only models (no protocol schema).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import JsonValue


@dataclass(frozen=True)
class Measurement:
    """A dimension's raw result before it is scored against a threshold."""

    name: str
    score: float
    detail: str = ""


@dataclass(frozen=True)
class DimensionResult:
    name: str
    score: float
    passed: bool
    threshold: float
    detail: str = ""


@dataclass(frozen=True)
class Delta:
    name: str
    score: float
    baseline: float
    delta: float


@dataclass(frozen=True)
class BenchmarkReport:
    dimensions: tuple[DimensionResult, ...]
    elapsed_ms: float

    @property
    def passed(self) -> bool:
        return all(dimension.passed for dimension in self.dimensions)

    def scores(self) -> dict[str, float]:
        return {dimension.name: dimension.score for dimension in self.dimensions}

    def score(self, name: str) -> float:
        return next(d.score for d in self.dimensions if d.name == name)

    def compare(self, baseline: Mapping[str, float]) -> tuple[Delta, ...]:
        """Score deltas vs a pinned baseline — the comparable-across-changes view."""
        return tuple(
            Delta(
                name=d.name,
                score=d.score,
                baseline=baseline.get(d.name, 0.0),
                delta=round(d.score - baseline.get(d.name, 0.0), 4),
            )
            for d in self.dimensions
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "passed": self.passed,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "threshold": d.threshold,
                    "passed": d.passed,
                    "detail": d.detail,
                }
                for d in self.dimensions
            ],
        }

    def format_table(self) -> str:
        lines = [f"{'dimension':<20}{'score':>7}{'thr':>7}  status", "-" * 44]
        for d in self.dimensions:
            lines.append(
                f"{d.name:<20}{d.score:>7.2f}{d.threshold:>7.2f}  {'ok' if d.passed else 'FAIL'}"
            )
        verdict = "PASS" if self.passed else "REGRESSED"
        lines.append("-" * 44)
        lines.append(f"{'':<20}{'':>7}{'':>7}  {verdict} ({self.elapsed_ms:.0f} ms)")
        return "\n".join(lines)
