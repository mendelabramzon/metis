"""Retrieval relevance: the top-k retrieval for each golden query contains the expected evidence."""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    hits = 0
    for query in workspace.queries:
        retrieved = engine.retrieve(query.text, k=3, ceiling=query.max_sensitivity)
        text = " ".join(claim.text for claim in retrieved)
        if all(expected in text for expected in query.expects):
            hits += 1
    total = len(workspace.queries)
    score = hits / total if total else 0.0
    return Measurement("retrieval", score, f"{hits}/{total} queries retrieved expected evidence")
