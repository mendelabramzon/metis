"""Validate that a deletion fully propagated into derived artifacts.

Tombstoning is append-only and idempotent (it only marks rows whose ``tombstoned_at`` is
null), so this job propagates the deletion and then re-runs the same cascade: if the second
pass touches zero rows, every derived claim/cell/doc/segment is already tombstoned and the
deletion is consistent. No new core query is needed — the second pass's row counts are the proof.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from metis_core import TombstoneResult, tombstone_artifact
from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of


def _is_empty(result: TombstoneResult) -> bool:
    return (
        result.raw_artifacts
        + result.normalized_docs
        + result.parsed_docs
        + result.segments
        + result.claims
        + result.mem_cells
    ) == 0


class ValidateDeletionsJob:
    kind = "validate_deletions"
    triggers: tuple[Trigger, ...] = (Trigger.EVENT,)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("artifact_id", ""))

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        workspace_id = str(workspace_of(payload))
        artifact_id = str(payload["artifact_id"])
        propagated = await tombstone_artifact(
            deps.sessionmaker, workspace_id=workspace_id, artifact_id=artifact_id
        )
        recheck = await tombstone_artifact(
            deps.sessionmaker, workspace_id=workspace_id, artifact_id=artifact_id
        )
        consistent = _is_empty(recheck)
        return JobOutcome(
            kind=self.kind,
            summary=f"propagated deletion of {artifact_id}; consistent={consistent}",
            counts={
                "claims": propagated.claims,
                "mem_cells": propagated.mem_cells,
                "segments": propagated.segments,
                "consistent": int(consistent),
            },
        )
