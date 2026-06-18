"""Measure retrieval quality (span recall@k) on its own — no answer generation involved.

The point of this harness is the separation the plan calls for: retrieval relevance is scored
purely from what the hybrid memory lookup returns (the source spans of retrieved cells vs. the
golden spans), independent of any LLM answer. It reuses the Stage 5 golden corpus and loader.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.llm import ModelCaller
from metis_core.memory_index import EmbeddingRouter, MemoryIndexLookup
from metis_eval.memory import Corpus, golden_workspace, load_corpus


@dataclass(frozen=True)
class RetrievalReport:
    k: int
    recall: float
    per_question: tuple[tuple[str, float], ...]


async def run_retrieval_eval(
    sessionmaker: async_sessionmaker[AsyncSession],
    router: EmbeddingRouter,
    *,
    corpus: Corpus | None = None,
    caller: ModelCaller | None = None,
    ks: tuple[int, ...] = (1, 3),
) -> dict[int, RetrievalReport]:
    corpus = corpus if corpus is not None else golden_workspace()
    await load_corpus(sessionmaker, router, corpus, caller=caller)
    lookup = MemoryIndexLookup(sessionmaker, router)

    reports: dict[int, RetrievalReport] = {}
    for k in ks:
        scored: list[tuple[str, float]] = []
        for question in corpus.questions:
            expected = corpus.expected_spans[question.query]
            hits = await lookup.search_mem_cells(
                workspace_id=corpus.workspace_id, query_text=question.query, k=k
            )
            retrieved = {str(ref.source_span_id) for hit in hits for ref in hit.item.source_spans}
            scored.append((question.query, len(retrieved & expected) / len(expected)))
        reports[k] = RetrievalReport(
            k=k, recall=_mean(score for _, score in scored), per_question=tuple(scored)
        )
    return reports


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0
