"""The runtime job registry: map each job ``kind`` to its handler instance."""

from __future__ import annotations

from metis_runtime.jobs.base import RuntimeJob
from metis_runtime.jobs.research import ResearchJob


def build_runtime_registry() -> dict[str, RuntimeJob]:
    jobs: list[RuntimeJob] = [ResearchJob()]
    return {job.kind: job for job in jobs}
