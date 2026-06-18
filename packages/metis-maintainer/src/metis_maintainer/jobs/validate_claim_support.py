"""Validate that a derived wiki statement still has claim support.

The wiki is a projection, never machine truth: every substantive statement must be backed by
claim ids (or explicitly marked unresolved). This check rejects a patch that asserts body
content while citing no claims, and flags inline footnote citations with no backing claim.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_protocol import MemoryScope, WikiPatch

_INLINE_CITATION = re.compile(r"\[\^([^\]]+)\]:")  # a footnote *definition*, e.g. "[^1]: ..."


def claim_support_issues(patch: WikiPatch) -> Sequence[str]:
    """Issues with the patch's claim support; empty means every statement is supported."""
    body = (patch.body_markdown or "").strip()
    if not body:
        return []
    issues: list[str] = []
    if not patch.claims:
        issues.append("wiki body has content but cites no claims")
    citation_count = len(set(_INLINE_CITATION.findall(patch.body_markdown or "")))
    if citation_count > len(patch.claims):
        issues.append(
            f"{citation_count} footnote citation(s) but only {len(patch.claims)} claim ref(s)"
        )
    return issues


def is_supported(patch: WikiPatch) -> bool:
    return not claim_support_issues(patch)


class ValidateClaimSupportJob:
    """Health check: every live MemCell should still rest on at least one live claim.

    A reporting job (no mutation): tombstone propagation normally keeps this at zero, so a
    non-zero count signals an inconsistency to investigate. Idempotent by construction.
    """

    kind = "validate_claim_support"
    triggers: tuple[Trigger, ...] = (Trigger.PERIODIC,)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("bucket") or "")

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        cells = await deps.memory_store.query_cells(MemoryScope(workspace_id=workspace_of(payload)))
        unsupported = 0
        for cell in cells:
            live = [
                ref for ref in cell.claims if await deps.claim_store.get(ref.claim_id) is not None
            ]
            if cell.claims and not live:
                unsupported += 1
        return JobOutcome(
            kind=self.kind,
            summary=f"{unsupported} of {len(cells)} cell(s) lack live claim support",
            counts={"cells": len(cells), "unsupported": unsupported},
        )
