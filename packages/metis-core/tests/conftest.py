"""Shared testcontainers fixtures for the metis-core suite.

A session-scoped Postgres (pgvector) + MinIO are started once and migrated; each
test gets a fresh per-function async engine with all tables truncated. If no Docker
daemon is available the container fixtures skip, so the pure-Python tests (policy)
still run.
"""

from __future__ import annotations

import os

# Disable the testcontainers Ryuk reaper before importing testcontainers: our
# fixtures stop their containers explicitly, and Ryuk's port mapping is flaky on
# Docker Desktop.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer

from metis_core.db.engine import make_engine, make_sessionmaker
from metis_core.dev.testing import (
    async_url,
    docker_available,
    make_minio,
    make_postgres,
    minio_settings,
    run_upgrade,
    truncate_all,
)
from metis_core.objectstore import S3ObjectStore


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    if not docker_available():
        pytest.skip("Docker is not available")
    container = make_postgres()
    container.start()
    try:
        run_upgrade(async_url(container))  # migrate once for the whole session
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


@pytest.fixture(scope="session")
def db_url(postgres: PostgresContainer) -> str:
    return async_url(postgres)


@pytest.fixture(scope="session")
def object_store(minio: MinioContainer) -> S3ObjectStore:
    endpoint, access_key, secret_key = minio_settings(minio)
    store = S3ObjectStore(
        bucket="metis-test",
        endpoint_url=endpoint,
        region="us-east-1",
        access_key=access_key,
        secret_key=secret_key,
    )
    asyncio.run(store.ensure_bucket())
    return store


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(db_url)
    await truncate_all(engine)  # isolate each test
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)
