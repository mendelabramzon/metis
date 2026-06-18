"""Prompts and output schemas for the LLM-backed query steps (rewrite, answer).

These DTOs are runtime-internal scratch shapes (not registered protocol schemas), lenient
about extra keys. ``query_registry`` extends the baseline registry so a model caller can be
wired for ``query_rewrite``/``query_answer``; the deterministic fallbacks need no registry.
"""

from __future__ import annotations

from pydantic import ConfigDict

from metis_core.llm import PromptRegistry, default_registry
from metis_core.llm.prompts import PromptTemplate
from metis_protocol import ModelTaskClass, VersionedModel


class RewrittenQuery(VersionedModel):
    model_config = ConfigDict(extra="ignore")

    query: str


class AnswerDraft(VersionedModel):
    model_config = ConfigDict(extra="ignore")

    answer: str


_QUERY_REWRITE = PromptTemplate(
    task_class=ModelTaskClass.QUERY_REWRITE,
    version="1",
    system=(
        "Rewrite the user's question into a single, self-contained search query that surfaces the "
        'evidence needed to answer it. Do not answer it. Return JSON: {"query": "..."}.'
    ),
)

_QUERY_ANSWER = PromptTemplate(
    task_class=ModelTaskClass.QUERY_ANSWER,
    version="1",
    system=(
        "Answer the question using ONLY the provided context. Cite nothing you were not given, "
        "and if the context conflicts, say so explicitly rather than choosing a side. If the "
        "context is insufficient, say you do not have enough evidence. "
        'Return JSON: {"answer": "..."}.'
    ),
)


def query_registry() -> PromptRegistry:
    """The baseline registry plus the query rewrite/answer prompts."""
    registry = default_registry()
    registry.register(_QUERY_REWRITE)
    registry.register(_QUERY_ANSWER)
    return registry
