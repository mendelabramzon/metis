"""Parse quality: every golden document normalizes to non-empty text."""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    parsed = sum(1 for ingested in engine.docs if ingested.doc.text.strip())
    total = len(engine.docs)
    score = parsed / total if total else 0.0
    return Measurement("parse_quality", score, f"{parsed}/{total} documents parsed to text")
