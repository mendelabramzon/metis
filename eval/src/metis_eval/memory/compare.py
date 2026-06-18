"""Memory retrieval vs. naive chunk retrieval on the golden workspace.

Loads the corpus into the durable substrate, consolidates each document into a MemCell and
indexes it, indexes the raw chunks as the naive baseline, then scores both retrievers on the
golden questions with **span coverage@k**: of the source spans that jointly answer a question,
what fraction appear in the evidence of the top-``k`` results. A consolidated MemCell carries
a whole document's spans, so it can cover a multi-fact question in one hit where a single
chunk cannot — which is exactly the headline the metric is meant to expose.

The retriever, embedder, and optional model caller are all injected, so the same harness runs
deterministically with the stub embedder (CI) and against local Ollama models (bge-m3 +
gemma4) for a real-quality read.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.llm import ModelCaller
from metis_core.mappers import (
    normalized_doc_to_row,
    parsed_doc_to_row,
    raw_artifact_to_row,
    segment_to_row,
)
from metis_core.memory_index import EmbeddingRouter, MemoryIndexer, MemoryIndexLookup
from metis_core.stores import PostgresMemoryStore
from metis_eval.memory.fixtures import Corpus, golden_workspace
from metis_maintainer.memory import MemCellBuilder


@dataclass(frozen=True)
class QuestionScore:
    query: str
    memory_coverage: float
    naive_coverage: float


@dataclass(frozen=True)
class EvalReport:
    k: int
    scores: tuple[QuestionScore, ...]

    @property
    def memory_coverage(self) -> float:
        return _mean(score.memory_coverage for score in self.scores)

    @property
    def naive_coverage(self) -> float:
        return _mean(score.naive_coverage for score in self.scores)

    @property
    def memory_wins(self) -> bool:
        return self.memory_coverage > self.naive_coverage


async def run_memory_eval(
    sessionmaker: async_sessionmaker[AsyncSession],
    router: EmbeddingRouter,
    *,
    corpus: Corpus | None = None,
    caller: ModelCaller | None = None,
    ks: tuple[int, ...] = (1, 2, 3),
) -> dict[int, EvalReport]:
    corpus = corpus if corpus is not None else golden_workspace()
    await _load(sessionmaker, router, corpus, caller=caller)
    lookup = MemoryIndexLookup(sessionmaker, router)

    reports: dict[int, EvalReport] = {}
    for k in ks:
        scores: list[QuestionScore] = []
        for question in corpus.questions:
            expected = corpus.expected_spans[question.query]
            memory_hits = await lookup.search_mem_cells(
                workspace_id=corpus.workspace_id, query_text=question.query, k=k
            )
            memory_covered = {
                str(ref.source_span_id) for hit in memory_hits for ref in hit.item.source_spans
            }
            naive_hits = await lookup.search_segments(
                workspace_id=corpus.workspace_id, query_text=question.query, k=k
            )
            naive_covered = {
                corpus.seg_to_span[str(hit.item.id)]
                for hit in naive_hits
                if str(hit.item.id) in corpus.seg_to_span
            }
            scores.append(
                QuestionScore(
                    query=question.query,
                    memory_coverage=len(memory_covered & expected) / len(expected),
                    naive_coverage=len(naive_covered & expected) / len(expected),
                )
            )
        reports[k] = EvalReport(k=k, scores=tuple(scores))
    return reports


async def _load(
    sessionmaker: async_sessionmaker[AsyncSession],
    router: EmbeddingRouter,
    corpus: Corpus,
    *,
    caller: ModelCaller | None,
) -> None:
    # Evidence rows first, parents before children (FKs are non-deferrable).
    async with unit_of_work(sessionmaker) as session:
        session.add_all([raw_artifact_to_row(raw) for raw in corpus.raw_artifacts])
        await session.flush()
        session.add_all([normalized_doc_to_row(doc) for doc in corpus.normalized_docs])
        await session.flush()
        session.add_all([parsed_doc_to_row(doc) for doc in corpus.parsed_docs])
        await session.flush()
        session.add_all([segment_to_row(segment) for segment in corpus.segments])

    store = PostgresMemoryStore(sessionmaker)
    builder = MemCellBuilder(caller=caller)
    indexer = MemoryIndexer(sessionmaker, router)
    for claims in corpus.doc_claims.values():
        cell = await builder.build(workspace_id=corpus.workspace_id, claims=claims)
        await store.write_mem_cell(cell)
        await indexer.index_mem_cell(cell)
    await indexer.index_segments(corpus.segments)  # the naive baseline index


def format_reports(reports: dict[int, EvalReport]) -> str:
    """A compact table of memory vs. naive coverage at each k (for manual/Ollama runs)."""
    lines = [f"{'k':>3}  {'memory':>8}  {'naive':>8}  winner", "  " + "-" * 34]
    for k in sorted(reports):
        report = reports[k]
        winner = (
            "memory"
            if report.memory_wins
            else ("naive" if report.naive_coverage > report.memory_coverage else "tie")
        )
        lines.append(
            f"{k:>3}  {report.memory_coverage:>8.2f}  {report.naive_coverage:>8.2f}  {winner}"
        )
    return "\n".join(lines)


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0
