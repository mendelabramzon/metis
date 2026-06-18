"""Retrieval recall is measured on the golden corpus, separately from any answer."""

from metis_core.memory_index import stub_router
from metis_eval.retrieval import run_retrieval_eval


async def test_memory_retrieval_recall_on_golden_questions(sessionmaker) -> None:
    reports = await run_retrieval_eval(sessionmaker, stub_router())
    # The consolidated cell for a document carries all its spans, so a single retrieved cell
    # covers a multi-fact question's spans: recall@1 is perfect on the golden set.
    assert reports[1].recall == 1.0
    assert all(0.0 <= recall <= 1.0 for _, recall in reports[1].per_question)
