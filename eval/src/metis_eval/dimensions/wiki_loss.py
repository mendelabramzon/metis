"""Wiki compilation loss: the diagnostic probes survive compilation into a wiki page."""

from __future__ import annotations

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement
from metis_protocol import Sensitivity


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    # Compile a minimal page from the (visible) claims, then probe for facts that must survive.
    page = "\n".join(
        f"- {claim.text}" for claim in engine.live_claims(ceiling=Sensitivity.INTERNAL)
    )
    survived = sum(1 for probe in workspace.wiki_probes if probe in page)
    total = len(workspace.wiki_probes)
    score = survived / total if total else 0.0
    return Measurement("wiki_loss", score, f"{survived}/{total} probes survived compilation")
