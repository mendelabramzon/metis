"""Aggregated service health: probe each dependency and report overall readiness.

A health check is only useful if it reflects *real* dependency health, so this aggregates injected
probes (Postgres, object store, model runtime) rather than returning a static "ok". Overall status
is the worst of the parts — ``UP`` only if every dependency answers, else ``DEGRADED`` (some down)
or ``DOWN`` (all down), with the failing component named. Enough for an operator's dashboard and
for an orchestrator's readiness gate. A probe that raises is treated as unhealthy, never a 500.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import JsonValue


class HealthStatus(StrEnum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    healthy: bool
    detail: str = ""


@dataclass(frozen=True)
class HealthReport:
    status: HealthStatus
    components: tuple[ComponentHealth, ...]

    @property
    def ok(self) -> bool:
        return self.status is HealthStatus.UP

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status.value,
            "components": [
                {"name": c.name, "healthy": c.healthy, "detail": c.detail} for c in self.components
            ],
        }


#: A probe pings one dependency; raising or returning None means it is down.
Ping = Callable[[], Awaitable[None]]


def liveness_probe(name: str, ping: Ping) -> Callable[[], Awaitable[ComponentHealth]]:
    """Wrap a dependency ping into a probe that never raises (a failure is reported, not thrown)."""

    async def _probe() -> ComponentHealth:
        try:
            await ping()
        except Exception as exc:  # a dependency being down must not crash the health endpoint
            return ComponentHealth(name=name, healthy=False, detail=f"{type(exc).__name__}: {exc}")
        return ComponentHealth(name=name, healthy=True)

    return _probe


class HealthChecker:
    """Runs every dependency probe and folds the results into one report."""

    def __init__(self, probes: Mapping[str, Ping]) -> None:
        self._probes = {name: liveness_probe(name, ping) for name, ping in probes.items()}

    async def check(self) -> HealthReport:
        components = tuple([await probe() for probe in self._probes.values()])
        healthy = [component.healthy for component in components]
        if not healthy or all(healthy):
            status = HealthStatus.UP
        elif any(healthy):
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.DOWN
        return HealthReport(status=status, components=components)
