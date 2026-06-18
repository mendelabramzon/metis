"""Claim-extraction accuracy: recall of the expected facts over the extracted claims."""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement
from metis_protocol import Sensitivity


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    texts = [claim.text for claim in engine.live_claims(ceiling=Sensitivity.INTERNAL)]
    found = sum(1 for fact in workspace.expected_facts if any(fact in text for text in texts))
    total = len(workspace.expected_facts)
    score = found / total if total else 0.0
    return Measurement("claim_extraction", score, f"{found}/{total} expected facts extracted")
