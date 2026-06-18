"""Contradiction detection: the injected conflicting founding year is surfaced, not merged away."""

from __future__ import annotations

import re

from metis_eval.engine import GoldenEngine
from metis_eval.golden import GoldenWorkspace
from metis_eval.report import Measurement
from metis_protocol import Sensitivity

_YEAR = re.compile(r"(?:19|20)\d{2}")


async def evaluate(workspace: GoldenWorkspace, engine: GoldenEngine) -> Measurement:
    subject = workspace.contradiction_subject.lower()
    years: set[str] = set()
    for claim in engine.live_claims(ceiling=Sensitivity.RESTRICTED):
        lowered = claim.text.lower()
        if "founded" in lowered and subject in lowered:
            years.update(_YEAR.findall(claim.text))
    detected = len(years) > 1  # the same fact asserted with conflicting values
    return Measurement(
        "contradiction",
        1.0 if detected else 0.0,
        f"founding years for {workspace.contradiction_subject}: {sorted(years)}",
    )
