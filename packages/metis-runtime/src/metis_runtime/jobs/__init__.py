"""Runtime background jobs: the worker framework + the registered job handlers.

The runtime worker leases jobs from the durable queue and dispatches them to the engines (Stage 8
query/answer) the gateway otherwise runs inline, so long-running work runs off the request path.
Mirrors the maintainer worker's framework (``base`` + ``registry`` + ``runner``).
"""

from __future__ import annotations

from metis_runtime.jobs.base import (
    RuntimeDeps,
    RuntimeJob,
    RuntimeJobOutcome,
    build_runtime_deps,
    workspace_of,
)
from metis_runtime.jobs.registry import build_runtime_registry
from metis_runtime.jobs.research import RESEARCH_JOB_KIND, ResearchJob, build_research_job
from metis_runtime.jobs.runner import RuntimeWorker, UnknownRuntimeJobError

__all__ = [
    "RESEARCH_JOB_KIND",
    "ResearchJob",
    "RuntimeDeps",
    "RuntimeJob",
    "RuntimeJobOutcome",
    "RuntimeWorker",
    "UnknownRuntimeJobError",
    "build_research_job",
    "build_runtime_deps",
    "build_runtime_registry",
    "workspace_of",
]
