"""Diagnostic probes: did compilation drop a supported fact?

The central WiCER risk is lossy compilation. Each input claim is a probe: it is *covered* iff
the compiled patch both cites it (a claim ref) and prints its id in the body's citation footer.
``ProbeResult`` reports coverage and the loss fraction, which the refine loop gates on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from metis_protocol import Claim, WikiPatch


@dataclass(frozen=True)
class ProbeResult:
    covered: tuple[str, ...]
    dropped: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.covered) + len(self.dropped)

    @property
    def loss(self) -> float:
        return len(self.dropped) / self.total if self.total else 0.0

    @property
    def complete(self) -> bool:
        return not self.dropped


def probe_patch(patch: WikiPatch, expected: Sequence[Claim]) -> ProbeResult:
    """Probe whether every expected claim survived compilation into ``patch``."""
    cited = {str(ref.claim_id) for ref in patch.claims}
    body = patch.body_markdown or ""
    covered: list[str] = []
    dropped: list[str] = []
    for claim in expected:
        claim_id = str(claim.id)
        if claim_id in cited and claim_id in body:
            covered.append(claim_id)
        else:
            dropped.append(claim_id)
    return ProbeResult(covered=tuple(covered), dropped=tuple(dropped))
