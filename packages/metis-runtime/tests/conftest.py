"""Testcontainers Postgres + a wired QueryEngine and a seed helper for the runtime suite."""

from __future__ import annotations

import os

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from pathlib import Path

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
from metis_core.memory_index import MemoryIndexer, MemoryIndexLookup, stub_router
from metis_core.stores import PostgresClaimStore, PostgresMemoryStore
from metis_protocol import (
    AuditEvent,
    BatchId,
    Claim,
    ContextBundle,
    ContextBundleId,
    ExtractionBatch,
    MemCell,
    QueryId,
    new_id,
)
from metis_protocol.examples import PDOC, PROV, WS
from metis_runtime.query import MemoryRetriever, QueryEngine
from metis_runtime.skills import SkillRegistry, SkillRunner

_SKILLS_FIXTURES = Path(__file__).parent / "fixtures" / "skills"


class MemoryObjectStore:
    """An in-process ObjectStore (the protocol) for skill artifact capture in tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_bytes(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return key

    async def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class RecordingAuditSink:
    """An in-process AuditSink (the protocol) that records emitted events for assertions."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    if not docker_available():
        pytest.skip("Docker is not available")
    container = make_postgres()
    container.start()
    try:
        run_upgrade(async_url(container))
        yield container
    finally:
        container.stop()


@pytest.fixture
async def engine(postgres: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(async_url(postgres))
    await truncate_all(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)


@pytest.fixture
def retriever(sessionmaker: async_sessionmaker[AsyncSession]) -> MemoryRetriever:
    return MemoryRetriever(MemoryIndexLookup(sessionmaker, stub_router()))


@pytest.fixture
def query_engine(
    sessionmaker: async_sessionmaker[AsyncSession], retriever: MemoryRetriever
) -> QueryEngine:
    return QueryEngine(retriever=retriever, claim_store=PostgresClaimStore(sessionmaker))


@pytest.fixture
def seed(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Callable[[MemCell, Sequence[Claim]], Awaitable[None]]:
    """Write the cited claims, the cell, and the cell's embedding (stub) — one episode."""
    memory = PostgresMemoryStore(sessionmaker)
    claims_store = PostgresClaimStore(sessionmaker)
    indexer = MemoryIndexer(sessionmaker, stub_router())

    async def _seed(cell: MemCell, claims: Sequence[Claim]) -> None:
        if claims:
            await claims_store.write(
                ExtractionBatch(
                    id=new_id(BatchId),
                    workspace_id=WS,
                    parsed_doc_id=PDOC,
                    provenance=PROV,
                    claims=tuple(claims),
                )
            )
        await memory.write_mem_cell(cell)
        await indexer.index_mem_cell(cell)

    return _seed


@pytest.fixture
def bundle() -> ContextBundle:
    return ContextBundle(id=new_id(ContextBundleId), query_id=new_id(QueryId), sections=())


@pytest.fixture
def skill_registry() -> SkillRegistry:
    return SkillRegistry.discover(_SKILLS_FIXTURES)


@pytest.fixture
def object_store() -> MemoryObjectStore:
    return MemoryObjectStore()


@pytest.fixture
def audit_sink() -> RecordingAuditSink:
    return RecordingAuditSink()


@pytest.fixture
def skill_runner(
    skill_registry: SkillRegistry,
    object_store: MemoryObjectStore,
    audit_sink: RecordingAuditSink,
) -> SkillRunner:
    return SkillRunner(
        skill_registry,
        audit_sink=audit_sink,
        object_store=object_store,
        workspace_id=WS,
        secrets={"METIS_TEST_SECRET": "s3cr3t"},
    )
