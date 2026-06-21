"""metis-runtime: retrieval, memory use, and skill execution for answers/actions.

Stage 8 implements the query/answer runtime under :mod:`metis_runtime.query` — the
``QueryEngine`` and its plan -> retrieve -> pack -> verify -> answer -> verify-citations
pipeline, composing the Stage 5 hybrid memory lookup. Stage 9 (:mod:`metis_runtime.skills`)
runs skills safely, and Stage 10 (:mod:`metis_runtime.agent`) is the ``AgentLoop`` that combines
all three into an action-capable assistant. May import ``metis_protocol``, ``metis_core``, and
``metis_skills``.
"""

from __future__ import annotations

from metis_runtime.agent import (
    AgentLoop,
    AgentRequest,
    AgentRun,
    TaskStatus,
    Trust,
)
from metis_runtime.jobs import (
    RESEARCH_JOB_KIND,
    RuntimeDeps,
    RuntimeJobOutcome,
    RuntimeWorker,
    build_research_job,
    build_runtime_deps,
    build_runtime_registry,
)
from metis_runtime.query import (
    Answer,
    AnswerGenerator,
    BudgetedContextPacker,
    MemoryRetriever,
    QueryEngine,
    propose_fileback,
    query_registry,
    verify_citations,
)

__version__ = "0.0.0"

__all__ = [
    "RESEARCH_JOB_KIND",
    "AgentLoop",
    "AgentRequest",
    "AgentRun",
    "Answer",
    "AnswerGenerator",
    "BudgetedContextPacker",
    "MemoryRetriever",
    "QueryEngine",
    "RuntimeDeps",
    "RuntimeJobOutcome",
    "RuntimeWorker",
    "TaskStatus",
    "Trust",
    "__version__",
    "build_research_job",
    "build_runtime_deps",
    "build_runtime_registry",
    "propose_fileback",
    "query_registry",
    "verify_citations",
]
