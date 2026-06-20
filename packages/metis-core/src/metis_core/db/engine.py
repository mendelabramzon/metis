"""Async engine and sessionmaker factories (asyncpg driver, ADR 0008)."""

from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True, future=True)


def to_sync_url(database_url: str) -> str:
    """The sync (psycopg2) form of a database URL — the stores run on asyncpg, but the secret store
    is a small sync component (the ``SecretStore`` interface is sync), so it talks psycopg2 to the
    same Postgres. A URL that is already sync is returned unchanged."""
    url = make_url(database_url)
    if url.drivername.endswith("+asyncpg"):
        url = url.set(drivername="postgresql+psycopg2")
    return url.render_as_string(hide_password=False)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False keeps returned ORM objects usable after commit.
    return async_sessionmaker(engine, expire_on_commit=False)
