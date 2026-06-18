"""Health checks reflect real dependency health: up when all probes pass, down when all fail."""

from __future__ import annotations

import asyncio

from metis_deploy import HealthChecker, HealthStatus, liveness_probe


async def _up() -> None:
    return None


async def _down() -> None:
    raise ConnectionError("connection refused")


async def test_all_dependencies_up_is_up() -> None:
    report = await HealthChecker(
        {"postgres": _up, "object_store": _up, "model_runtime": _up}
    ).check()
    assert report.status is HealthStatus.UP
    assert report.ok
    assert all(component.healthy for component in report.components)


async def test_one_dependency_down_is_degraded() -> None:
    report = await HealthChecker({"postgres": _up, "object_store": _down}).check()
    assert report.status is HealthStatus.DEGRADED
    failing = next(c for c in report.components if c.name == "object_store")
    assert not failing.healthy
    assert "connection refused" in failing.detail


async def test_all_dependencies_down_is_down() -> None:
    report = await HealthChecker({"postgres": _down, "object_store": _down}).check()
    assert report.status is HealthStatus.DOWN
    assert not report.ok


def test_probe_failure_is_reported_not_raised() -> None:
    component = asyncio.run(liveness_probe("db", _down)())
    assert component.healthy is False  # a down dependency is reported, never thrown
