"""Source-span accuracy: every claim's span slices back to exactly the claim text."""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    total = 0
    matched = 0
    for ingested in engine.docs:
        if ingested.deleted:
            continue
        for claim in ingested.claims:
            for ref in claim.source_spans:
                span = ingested.spans.get(str(ref.source_span_id))
                if span is None:
                    continue
                total += 1
                if ingested.doc.text[span.char_start : span.char_end] == claim.text:
                    matched += 1
    score = matched / total if total else 0.0
    return Measurement("span_accuracy", score, f"{matched}/{total} spans slice to their claim text")
