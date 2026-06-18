"""The query/answer pipeline: plan -> retrieve -> pack -> verify -> answer -> verify citations.

Retrieval composes the Stage 5 hybrid memory lookup; answering is grounded, sensitivity-bounded,
contradiction-aware, and uncertainty-honest. Tool/skill use is Stage 9; the agent loop is Stage 10.
"""

from __future__ import annotations

from metis_runtime.query.answer import Answer, AnswerGenerator, conflict_notes
from metis_runtime.query.api import QueryEngine
from metis_runtime.query.cite_verify import CitationCheck, verify_citations
from metis_runtime.query.fileback import FilebackProposal, propose_fileback
from metis_runtime.query.pack import BudgetedContextPacker
from metis_runtime.query.plan import QueryPlan, plan_query
from metis_runtime.query.prompts import query_registry
from metis_runtime.query.retrievers import MemoryRetriever
from metis_runtime.query.rewrite import rewrite_query
from metis_runtime.query.sufficiency import Sufficiency, assess_sufficiency

__all__ = [
    "Answer",
    "AnswerGenerator",
    "BudgetedContextPacker",
    "CitationCheck",
    "FilebackProposal",
    "MemoryRetriever",
    "QueryEngine",
    "QueryPlan",
    "Sufficiency",
    "assess_sufficiency",
    "conflict_notes",
    "plan_query",
    "propose_fileback",
    "query_registry",
    "rewrite_query",
    "verify_citations",
]
