"""Rebuild a Profile from the workspace's claims, tracking conflicts.

The profile is the current-state projection for a ``(scope, label)``, so a refresh upserts it.
Conflicting facts are kept as flagged facts and emitted as explicit contradictions (never
merged), reusing the Stage 5 ``ProfileBuilder``. Idempotent: stable profile/contradiction ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_protocol import ClaimFilter, ProfileScope


class RefreshProfileJob:
    kind = "refresh_profile"
    triggers: tuple[Trigger, ...] = (Trigger.EVENT, Trigger.PERIODIC)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        scope = str(payload.get("scope", ProfileScope.WORKSPACE.value))
        label = str(payload.get("label", "workspace"))
        return f"{scope}:{label}:{payload.get('batch_id') or payload.get('bucket') or ''}"

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        workspace_id = workspace_of(payload)
        scope = ProfileScope(str(payload.get("scope", ProfileScope.WORKSPACE.value)))
        label = str(payload.get("label", "workspace"))
        claims = await deps.claim_store.query(ClaimFilter(workspace_id=workspace_id))
        if not claims:
            return JobOutcome(kind=self.kind, summary="no claims; nothing to profile")

        result = deps.profile_builder.build(scope=scope, label=label, claims=claims)
        await deps.memory_store.write_profile(result.profile)
        for contradiction in result.contradictions:
            await deps.memory_store.write_contradiction(contradiction)
        return JobOutcome(
            kind=self.kind,
            summary=f"profile '{label}' with {len(result.profile.facts)} fact(s)",
            counts={
                "facts": len(result.profile.facts),
                "contradictions": len(result.contradictions),
            },
        )
