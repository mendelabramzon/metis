"""The WiCER compile -> evaluate -> refine loop.

Compilation is never accepted blind: after each compile, diagnostic probes check that no
supported fact was dropped. If the probe is incomplete, the drop is recorded in the error book
and the compiler is re-invoked (a stochastic/LLM compiler can do better on retry; a complete
deterministic compiler converges on the first round). The loop returns the best patch and the
final probe so callers can gate approval on compilation loss.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from metis_maintainer.wiki.error_book import ErrorBook
from metis_maintainer.wiki.evaluate import ProbeResult, probe_patch
from metis_protocol import Claim, WikiPage, WikiPatch


class SupportsCompile(Protocol):
    async def compile(
        self,
        *,
        title: str,
        slug: str,
        claims: Sequence[Claim],
        existing: WikiPage | None = None,
    ) -> WikiPatch: ...


@dataclass(frozen=True)
class RefineResult:
    patch: WikiPatch
    rounds: int
    probe: ProbeResult


async def compile_with_refine(
    compiler: SupportsCompile,
    *,
    title: str,
    slug: str,
    claims: Sequence[Claim],
    existing: WikiPage | None = None,
    max_rounds: int = 3,
    error_book: ErrorBook | None = None,
) -> RefineResult:
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    patch: WikiPatch | None = None
    probe: ProbeResult | None = None
    for round_no in range(1, max_rounds + 1):
        patch = await compiler.compile(title=title, slug=slug, claims=claims, existing=existing)
        probe = probe_patch(patch, claims)
        if probe.complete:
            return RefineResult(patch=patch, rounds=round_no, probe=probe)
        if error_book is not None:
            error_book.record(slug=slug, dropped=probe.dropped)
    assert patch is not None  # the loop ran at least once (max_rounds >= 1)
    assert probe is not None
    return RefineResult(patch=patch, rounds=max_rounds, probe=probe)
