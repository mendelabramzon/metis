"""The headline Stage 5 metric: memory retrieval beats naive chunk retrieval.

The stub-embedder run is deterministic and gates the metric in CI. The Ollama run repeats it
with a real local embedding model (bge-m3) when one is reachable, for a real-quality read.
"""

from __future__ import annotations

import httpx
import pytest

from metis_core.memory_index import EmbeddingRouter, OllamaEmbedder, stub_router
from metis_eval.memory import format_reports, run_memory_eval

_OLLAMA_URL = "http://localhost:11434"


def _ollama_reachable() -> bool:
    try:
        httpx.get(f"{_OLLAMA_URL}/api/tags", timeout=1.0).raise_for_status()
    except Exception:
        return False
    return True


async def test_memory_beats_naive_chunk_retrieval(sessionmaker) -> None:
    reports = await run_memory_eval(sessionmaker, stub_router())

    at_one = reports[1]
    # A single consolidated MemCell covers a multi-fact question; a single chunk cannot.
    assert at_one.memory_coverage == 1.0
    assert at_one.naive_coverage < 1.0
    assert at_one.memory_wins, format_reports(reports)


@pytest.mark.skipif(not _ollama_reachable(), reason="local Ollama not reachable")
async def test_memory_beats_naive_with_local_embeddings(sessionmaker) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        router = EmbeddingRouter([OllamaEmbedder(client, base_url=_OLLAMA_URL)])
        reports = await run_memory_eval(sessionmaker, router)

    assert reports[1].memory_wins, format_reports(reports)
