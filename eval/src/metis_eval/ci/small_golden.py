"""CI-sized golden-workspace replay: run the benchmark, print the report, fail on regression.

Run with ``uv run python -m metis_eval.ci.small_golden``. Exits non-zero if any dimension fell below
its threshold, so it can gate CI within a small time/cost budget (full evals run on demand/nightly).
"""

from __future__ import annotations

import asyncio

from metis_eval.report import BenchmarkReport
from metis_eval.runner import run_benchmark
from metis_eval.thresholds import check_thresholds


async def replay() -> BenchmarkReport:
    return await run_benchmark()


def main() -> int:
    report = asyncio.run(replay())
    print(report.format_table())
    violations = check_thresholds(report)
    for violation in violations:
        print(f"REGRESSION {violation.name}: {violation.score:.2f} < {violation.threshold:.2f}")
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
