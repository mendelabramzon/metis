"""Testcontainers fixtures for the metis-maintainer suite.

Reuses the scope-agnostic helpers in ``metis_core.dev.testing`` (maintainer may import
core), so the DB-backed tests run against the same migrated pgvector image the core suite
uses. No MinIO here — the maintainer touches memory tables, not object storage. Falls back
to skipping when no Docker daemon is present.
"""

from __future__ import annotations

import os

# Disable the testcontainers Ryuk reaper before importing testcontainers (see core conftest).
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from metis_core.db.engine import make_engine, make_sessionmaker
from metis_core.dev.testing import (
    async_url,
    docker_available,
    make_postgres,
    run_upgrade,
    truncate_all,
)
from metis_maintainer import MaintainerDeps, build_deps


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
def db_url(postgres: PostgresContainer) -> str:
    return async_url(postgres)


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(db_url)
    await truncate_all(engine)  # isolate each test
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)


@pytest.fixture
def deps(sessionmaker: async_sessionmaker[AsyncSession]) -> MaintainerDeps:
    return build_deps(sessionmaker)  # caller=None -> deterministic, evidence-only builders
