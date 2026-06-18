"""Migrations apply from an empty database and reverse cleanly.

These run on a dedicated container (not the shared session one) and are synchronous,
since the migration helpers manage their own event loop.
"""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from metis_core.db.engine import make_engine
from metis_core.dev.testing import (
    async_url,
    docker_available,
    make_postgres,
    run_downgrade,
    run_upgrade,
)


async def _table_names(url: str) -> set[str]:
    engine = make_engine(url)
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        names = {row[0] for row in result}
    await engine.dispose()
    return names


@pytest.fixture(scope="module")
def fresh_url() -> Iterator[str]:
    if not docker_available():
        pytest.skip("Docker is not available")
    container = make_postgres()
    container.start()
    try:
        yield async_url(container)
    finally:
        container.stop()


def test_upgrade_creates_all_tables(fresh_url: str) -> None:
    run_upgrade(fresh_url)
    names = asyncio.run(_table_names(fresh_url))
    assert {"raw_artifacts", "claims", "mem_cells", "audit_events", "jobs"} <= names
    assert "alembic_version" in names


def test_downgrade_then_upgrade_is_clean_and_idempotent(fresh_url: str) -> None:
    run_upgrade(fresh_url)
    run_downgrade(fresh_url)
    assert "raw_artifacts" not in asyncio.run(_table_names(fresh_url))
    run_upgrade(fresh_url)
    assert "raw_artifacts" in asyncio.run(_table_names(fresh_url))
