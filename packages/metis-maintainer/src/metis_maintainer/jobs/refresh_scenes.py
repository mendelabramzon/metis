"""Refresh MemScenes: re-cluster the live cells and upsert the (recomputable) scene rollups.

Scenes are projections, so a refresh updates them in place (the store upserts by the
anchor-stable scene id). When an indexer is wired, the refreshed scene summary is re-embedded
so retrieval stays consistent with the new text. Re-running over unchanged cells is a no-op.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_protocol import MemoryScope


class RefreshScenesJob:
    kind = "refresh_scenes"
    triggers: tuple[Trigger, ...] = (Trigger.EVENT, Trigger.PERIODIC)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("mem_cell_id") or payload.get("bucket") or "")

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        scope = MemoryScope(workspace_id=workspace_of(payload))
        cells = await deps.memory_store.query_cells(scope)
        written = 0
        for cluster in deps.scene_builder.cluster(cells):
            scene = await deps.scene_builder.build(cluster)
            await deps.memory_store.write_scene(scene)
            if deps.indexer is not None:
                await deps.indexer.index_scene(scene)
            written += 1
        return JobOutcome(
            kind=self.kind,
            summary=f"refreshed {written} scene(s) from {len(cells)} cell(s)",
            counts={"scenes": written, "cells": len(cells)},
        )
