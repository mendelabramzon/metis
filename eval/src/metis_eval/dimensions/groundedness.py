"""Answer groundedness + citation correctness: cited claims are in the evidence and on-target.

Scored with the deterministic groundedness judge (the calibration anchor in ``judges``): a query is
grounded only if the answer is sufficient, every cited claim was actually retrieved, and the answer
hits the expected fact.
"""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.judges import deterministic_groundedness
from metis_eval.report import Measurement


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    answerable = [query for query in workspace.queries if query.answerable]
    grounded = 0
    for query in answerable:
        evidence = {
            str(claim.id)
            for claim in engine.retrieve(query.text, k=3, ceiling=query.max_sensitivity)
        }
        answer = await engine.answer(
            engine.query_request(query.text, ceiling=query.max_sensitivity)
        )
        judgment = deterministic_groundedness(answer, evidence)
        if judgment.grounded and all(expected in answer.text for expected in query.expects):
            grounded += 1
    total = len(answerable)
    score = grounded / total if total else 0.0
    return Measurement("groundedness", score, f"{grounded}/{total} answers grounded and on-target")
