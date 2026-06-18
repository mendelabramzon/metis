"""Evaluation dimensions: one module per quality/safety axis, scored over the golden workspace.

Each ``evaluate`` returns a :class:`~metis_eval.report.Measurement`; the runner stamps it against
its threshold. The ordered ``DIMENSIONS`` tuple is what the benchmark runs (the CI gate's scope).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from metis_eval.dimensions import (
    claim_extraction,
    contradiction,
    groundedness,
    parse_quality,
    policy,
    retrieval,
    skill_safety,
    span_accuracy,
    wiki_loss,
)
from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement

DimensionFn = Callable[[GoldenWorkspace, GoldenEngine], Awaitable[Measurement]]

#: The dimensions the benchmark runs, in report order.
DIMENSIONS: tuple[DimensionFn, ...] = (
    parse_quality.evaluate,
    claim_extraction.evaluate,
    span_accuracy.evaluate,
    retrieval.evaluate,
    groundedness.evaluate,
    contradiction.evaluate,
    wiki_loss.evaluate,
    skill_safety.evaluate,
    policy.evaluate,
)

__all__ = ["DIMENSIONS", "DimensionFn"]
