"""TestClient wiring for the gateway suite: an app over the in-memory backend, no external infra."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_SKILLS = Path(__file__).parent / "fixtures" / "skills"


@pytest.fixture
def settings() -> GatewaySettings:
    return GatewaySettings(
        skills_root=str(_SKILLS),
        operator_token="op-token",
        user_token="user-token",
        workspace_id="ws_" + "1" * 32,
    )


@pytest.fixture
def client(settings: GatewaySettings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def op() -> dict[str, str]:
    return {"Authorization": "Bearer op-token"}


@pytest.fixture
def user() -> dict[str, str]:
    return {"Authorization": "Bearer user-token"}
