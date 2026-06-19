"""TestClient wiring for the gateway suite: in-memory by default, Postgres for the durable test."""

from __future__ import annotations

import os

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer

from metis_core import make_engine, make_sessionmaker
from metis_core.dev.testing import (
    async_url,
    docker_available,
    make_minio,
    make_postgres,
    minio_settings,
    run_upgrade,
)
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


# --- Postgres-backed fixtures (the durable backend test) ---


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    if not docker_available():
        pytest.skip("Docker is not available")
    container = make_postgres()
    container.start()
    try:
        run_upgrade(async_url(container))  # migrate to head before the gateway connects
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def minio() -> Iterator[MinioContainer]:
    if not docker_available():
        pytest.skip("Docker is not available")
    container = make_minio()
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def pg_settings(
    postgres: PostgresContainer, minio: MinioContainer, monkeypatch: pytest.MonkeyPatch
) -> GatewaySettings:
    """Gateway settings for the Postgres backend, with core DB/object-store env pointed at the
    containers (build_postgres_backend reads METIS_CORE_*)."""
    endpoint, access_key, secret_key = minio_settings(minio)
    monkeypatch.setenv("METIS_CORE_DATABASE_URL", async_url(postgres))
    monkeypatch.setenv("METIS_CORE_OBJECT_STORE_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("METIS_CORE_OBJECT_STORE_ACCESS_KEY", access_key)
    monkeypatch.setenv("METIS_CORE_OBJECT_STORE_SECRET_KEY", secret_key)
    monkeypatch.setenv("METIS_CORE_OBJECT_STORE_BUCKET", "metis-gateway-test")
    return GatewaySettings(
        backend="postgres",
        operator_token="op-token",
        user_token="user-token",
        workspace_id="ws_" + "2" * 32,
    )


@pytest.fixture
def pg_sessionmaker(postgres: PostgresContainer):
    """A sessionmaker over the migrated test Postgres, for unit-testing durable gateway stores."""
    return make_sessionmaker(make_engine(async_url(postgres)))
