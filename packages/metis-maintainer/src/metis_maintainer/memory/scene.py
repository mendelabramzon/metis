"""Cluster MemCells into MemScenes and keep scene summaries incrementally fresh.

Clustering starts simple, as the plan prescribes: cells that share a claim are grouped
(claim-graph proximity), which is deterministic and cheap to reason about before heavier
graph methods are justified by the eval. Scene identity is anchored to the lowest cell id
in the founding cluster, so a scene keeps the same id as cells are added.

:meth:`SceneBuilder.add_cell` is the incremental path: it folds one new cell into the
existing summary (RAPTOR-style rollup) using only ``(scene, cell)`` — it never re-reads the
whole membership — so refreshing a scene is O(1) in the new evidence, not O(all cells).
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_core.llm import ModelCaller
from metis_maintainer.memory._build import maintainer_provenance, now_utc, stable_id
from metis_maintainer.memory.prompts import SceneSummary
from metis_protocol import (
    ClaimRef,
    MemCell,
    MemCellRef,
    MemScene,
    MemSceneId,
    ModelTaskClass,
    Sensitivity,
    WorkspaceId,
    max_sensitivity,
)


class SceneBuilder:
    def __init__(self, *, caller: ModelCaller | None = None) -> None:
        self._caller = caller

    def cluster(self, cells: Sequence[MemCell]) -> list[list[MemCell]]:
        """Group cells that are connected through shared claims (union-find)."""
        parent: dict[str, str] = {str(cell.id): str(cell.id) for cell in cells}

        def find(node: str) -> str:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(left: str, right: str) -> None:
            parent[find(left)] = find(right)

        claim_owner: dict[str, str] = {}
        for cell in cells:
            for ref in cell.claims:
                key = str(ref.claim_id)
                if key in claim_owner:
                    union(str(cell.id), claim_owner[key])
                else:
                    claim_owner[key] = str(cell.id)

        groups: dict[str, list[MemCell]] = {}
        for cell in cells:
            groups.setdefault(find(str(cell.id)), []).append(cell)
        return list(groups.values())

    async def build(self, cells: Sequence[MemCell], *, topic: str | None = None) -> MemScene:
        """Build one scene from a cluster of cells (title + summary over all of them)."""
        if not cells:
            raise ValueError("cannot build a MemScene from no cells")
        workspace_id = cells[0].provenance.workspace_id
        sensitivity = _ceiling(cells)
        summary = await self._summarize(
            workspace_id, existing=None, cells=cells, ceiling=sensitivity
        )
        anchor = min(str(cell.id) for cell in cells)
        occurred = [cell.occurred_at for cell in cells if cell.occurred_at is not None]
        return MemScene(
            id=stable_id(MemSceneId, f"{workspace_id}:{anchor}"),
            provenance=maintainer_provenance(
                workspace_id,
                agent="scene-builder",
                operation="consolidate_memory",
                inputs=[str(cell.id) for cell in cells],
            ),
            policy=cells[0].policy.model_copy(update={"sensitivity": sensitivity}),
            created_at=now_utc(),
            title=summary.title,
            summary=summary.summary,
            mem_cells=tuple(MemCellRef(mem_cell_id=cell.id) for cell in cells),
            claims=_union_claims(cells),
            topic=topic,
            started_at=min(occurred) if occurred else None,
            ended_at=max(occurred) if occurred else None,
        )

    async def add_cell(self, scene: MemScene, cell: MemCell) -> MemScene:
        """Incrementally fold one new cell into ``scene`` (no full recompute)."""
        if any(ref.mem_cell_id == cell.id for ref in scene.mem_cells):
            return scene  # already a member; nothing to fold
        sensitivity = _ceiling([cell], floor=scene.policy.sensitivity)
        summary = await self._summarize(
            scene.provenance.workspace_id, existing=scene.summary, cells=[cell], ceiling=sensitivity
        )
        occurred = [cell.occurred_at] if cell.occurred_at is not None else []
        started = [scene.started_at, *occurred]
        ended = [scene.ended_at, *occurred]
        return scene.model_copy(
            update={
                "title": summary.title,
                "summary": summary.summary,
                "mem_cells": (*scene.mem_cells, MemCellRef(mem_cell_id=cell.id)),
                "claims": _union_claims([cell], existing=scene.claims),
                "policy": scene.policy.model_copy(update={"sensitivity": sensitivity}),
                "started_at": min((value for value in started if value is not None), default=None),
                "ended_at": max((value for value in ended if value is not None), default=None),
            }
        )

    async def _summarize(
        self,
        workspace_id: WorkspaceId,
        *,
        existing: str | None,
        cells: Sequence[MemCell],
        ceiling: Sensitivity,
    ) -> SceneSummary:
        if self._caller is None:
            return _deterministic_scene_summary(existing, cells)
        return await self._caller.call_structured(
            task_class=ModelTaskClass.CONSOLIDATE_MEMORY,
            workspace_id=workspace_id,
            user_content=_render_scene(existing, cells),
            output_type=SceneSummary,
            sensitivity=ceiling,
        )


def _ceiling(cells: Sequence[MemCell], *, floor: Sensitivity = Sensitivity.PUBLIC) -> Sensitivity:
    return max_sensitivity(floor, *(cell.policy.sensitivity for cell in cells))


def _union_claims(
    cells: Sequence[MemCell], *, existing: tuple[ClaimRef, ...] = ()
) -> tuple[ClaimRef, ...]:
    seen: set[str] = set()
    out: list[ClaimRef] = []
    for ref in (*existing, *(ref for cell in cells for ref in cell.claims)):
        if str(ref.claim_id) not in seen:
            seen.add(str(ref.claim_id))
            out.append(ref)
    return tuple(out)


def _render_scene(existing: str | None, cells: Sequence[MemCell]) -> str:
    lines: list[str] = []
    if existing:
        lines += ["Current scene summary:", existing, ""]
    lines += ["Episodes:", *(f"- {cell.summary}" for cell in cells)]
    return "\n".join(lines)


def _deterministic_scene_summary(existing: str | None, cells: Sequence[MemCell]) -> SceneSummary:
    additions = " ".join(cell.summary for cell in cells)
    summary = f"{existing} {additions}".strip() if existing else additions
    title = (existing or cells[0].summary).split(".")[0][:80] if cells or existing else ""
    return SceneSummary(title=title, summary=summary)
