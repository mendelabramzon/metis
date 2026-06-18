"""Re-summarize MemCells when their supporting claims change — append-only supersession.

An episode is the set of claims from one source artifact. When that set changes (new claims
extracted, a claim removed), the rebuilt cell gets a different deterministic id, so this job
writes the new cell and supersedes the stale one with a memory patch. The prior cell stays
stored and auditable. Re-running with no change is a no-op (the current cell already exists).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_maintainer.memory import mark_supersedes, supersede_patch
from metis_protocol import Claim, ClaimFilter, MemCell, MemoryScope


def _by_artifact_claims(claims: Sequence[Claim]) -> dict[str, list[Claim]]:
    grouped: dict[str, list[Claim]] = {}
    for claim in claims:
        if claim.source_spans:
            grouped.setdefault(str(claim.source_spans[0].artifact_id), []).append(claim)
    return grouped


def _by_artifact_cells(cells: Sequence[MemCell]) -> dict[str, list[MemCell]]:
    grouped: dict[str, list[MemCell]] = {}
    for cell in cells:
        if cell.source_spans:
            grouped.setdefault(str(cell.source_spans[0].artifact_id), []).append(cell)
    return grouped


class ReviseEpisodesJob:
    kind = "revise_episodes"
    triggers: tuple[Trigger, ...] = (Trigger.EVENT,)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("artifact_id") or payload.get("batch_id") or "")

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        workspace_id = workspace_of(payload)
        scope = MemoryScope(workspace_id=workspace_id)
        claims_by_artifact = _by_artifact_claims(
            await deps.claim_store.query(ClaimFilter(workspace_id=workspace_id))
        )
        cells_by_artifact = _by_artifact_cells(await deps.memory_store.query_cells(scope))

        revised = 0
        for artifact_id, claims in claims_by_artifact.items():
            existing = cells_by_artifact.get(artifact_id, [])
            current = await deps.memcell_builder.build(workspace_id=workspace_id, claims=claims)
            if any(cell.id == current.id for cell in existing):
                continue  # the current episode is already materialized
            if existing:
                current = mark_supersedes(current, existing[0].id)
            await deps.memory_store.write_mem_cell(current)
            for stale in existing:
                await deps.memory_store.apply_patch(
                    supersede_patch(
                        superseded_id=stale.id, by_cell=current, reason="supporting claims changed"
                    )
                )
            revised += 1
        return JobOutcome(
            kind=self.kind,
            summary=f"revised {revised} episode(s)",
            counts={"revised": revised},
        )
