"""metis-runtime: retrieval, memory use, and skill execution for answers/actions.

Stage 8 implements the query/answer runtime under :mod:`metis_runtime.query` — the
``QueryEngine`` and its plan -> retrieve -> pack -> verify -> answer -> verify-citations
pipeline, composing the Stage 5 hybrid memory lookup. Skills (Stage 9) and the agent loop
(Stage 10) come next. May import ``metis_protocol``, ``metis_core``, and ``metis_skills``.
"""

from __future__ import annotations

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
    "Answer",
    "AnswerGenerator",
    "BudgetedContextPacker",
    "MemoryRetriever",
    "QueryEngine",
    "__version__",
    "propose_fileback",
    "query_registry",
    "verify_citations",
]
