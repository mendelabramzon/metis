"""Build time-bounded Foresights and expire ones past their validity window.

``TimelineForesightBuilder`` is the ``ForesightBuilder`` protocol impl: it flips foresights
whose window has closed to ``EXPIRED`` (tying expiry to the maintenance cadence) and builds a
fresh foresight from current claims. The new foresight's validity starts at the current UTC
day, so re-running on the same day produces the same id (idempotent upsert) rather than churn.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from metis_maintainer.jobs.base import JobOutcome, MaintainerDeps, Trigger, workspace_of
from metis_maintainer.memory import ForesightBuilder
from metis_maintainer.memory._build import now_utc
from metis_protocol import (
    ClaimFilter,
    ClaimStore,
    Foresight,
    ForesightStatus,
    MemoryScope,
    MemoryStore,
)


def _day_start(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


class TimelineForesightBuilder:
    """The ``ForesightBuilder`` protocol impl: expire stale foresights and build current ones."""

    def __init__(
        self,
        memory_store: MemoryStore,
        claim_store: ClaimStore,
        foresight_builder: ForesightBuilder,
        *,
        horizon_days: int = 90,
    ) -> None:
        self._memory = memory_store
        self._claims = claim_store
        self._builder = foresight_builder
        self._horizon = timedelta(days=horizon_days)

    async def build(self, scope: MemoryScope) -> Sequence[Foresight]:
        now = now_utc()
        refreshed: list[Foresight] = [
            existing.model_copy(update={"status": ForesightStatus.EXPIRED})
            for existing in await self._memory.query_foresights(scope)
            if existing.status is ForesightStatus.ACTIVE and existing.valid_to < now
        ]

        claims = await self._claims.query(ClaimFilter(workspace_id=scope.workspace_id))
        if claims:
            valid_from = _day_start(now)  # day-bucketed -> stable id within the day
            foresight = await self._builder.build(
                claims=claims, valid_from=valid_from, valid_to=valid_from + self._horizon
            )
            refreshed.append(foresight)
        return refreshed


class BuildForesightsJob:
    kind = "build_foresights"
    triggers: tuple[Trigger, ...] = (Trigger.PERIODIC,)

    def idempotency_key(self, payload: Mapping[str, Any]) -> str:
        return str(payload.get("bucket") or "")

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome:
        scope = MemoryScope(workspace_id=workspace_of(payload))
        builder = TimelineForesightBuilder(
            deps.memory_store, deps.claim_store, deps.foresight_builder
        )
        foresights = await builder.build(scope)
        expired = sum(1 for f in foresights if f.status is ForesightStatus.EXPIRED)
        for foresight in foresights:
            await deps.memory_store.write_foresight(foresight)
        return JobOutcome(
            kind=self.kind,
            summary=f"wrote {len(foresights)} foresight(s) ({expired} expired)",
            counts={"foresights": len(foresights), "expired": expired},
        )


if TYPE_CHECKING:
    from metis_protocol import ForesightBuilder as ForesightBuilderProtocol

    def _conforms(builder: TimelineForesightBuilder) -> ForesightBuilderProtocol:
        return builder  # static proof of the protocol
