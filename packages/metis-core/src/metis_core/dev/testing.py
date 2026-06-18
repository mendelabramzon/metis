"""Test infrastructure: ephemeral Postgres + MinIO via testcontainers.

Helpers here are scope-agnostic; the pytest fixtures that use them live in
``packages/metis-core/tests/conftest.py``. ``docker_available()`` lets the suite
skip cleanly when no Docker daemon is present.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer

from metis_core.db.base import Base

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def docker_available() -> bool:
    """True if a Docker daemon is reachable (testcontainers needs one)."""
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


def make_postgres() -> PostgresContainer:
    # pgvector image so `CREATE EXTENSION vector` works; psycopg2 for readiness only.
    return PostgresContainer("pgvector/pgvector:pg16", driver="psycopg2")


def make_minio() -> MinioContainer:
    return MinioContainer()


def async_url(postgres: PostgresContainer) -> str:
    """The container's URL rewritten to the asyncpg driver used by core."""
    return str(postgres.get_connection_url()).replace("psycopg2", "asyncpg")


def minio_settings(minio: MinioContainer) -> tuple[str, str, str]:
    """(endpoint_url, access_key, secret_key) for an S3 client."""
    host = minio.get_container_host_ip()
    port = minio.get_exposed_port(9000)
    return f"http://{host}:{port}", str(minio.access_key), str(minio.secret_key)


def make_alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config


def run_upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(make_alembic_config(url), revision)


def run_downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(make_alembic_config(url), revision)


async def truncate_all(engine: AsyncEngine) -> None:
    """Empty every table (keeps the schema) for per-test isolation."""
    names = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
