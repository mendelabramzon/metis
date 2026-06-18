"""Fixtures for the security suite: in-process fakes (Docker-free tests) + Postgres/MinIO (deletion,
audit integrity)."""

from __future__ import annotations

import os

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

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
from metis_protocol import (
    AuditEvent,
    ContextBundle,
    ContextBundleId,
    QueryId,
    QueryRequest,
    WorkspaceId,
    new_id,
)
from metis_runtime.agent import AgentLoop
from metis_runtime.query import Answer
from metis_runtime.skills import SkillRegistry, SkillRunner

WORKSPACE = WorkspaceId(f"ws_{'f' * 32}")
_SKILLS = Path(__file__).parent / "fixtures" / "skills"


@pytest.fixture
def workspace() -> WorkspaceId:
    return WORKSPACE


@pytest.fixture
def skills_root() -> Path:
    return _SKILLS


class InMemoryObjectStore:
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
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class FakeAnswerer:
    """Returns a fixed answer regardless of retrieval (the injected text can ride in ``text``)."""

    def __init__(self, *, text: str, sufficient: bool = True) -> None:
        self._text = text
        self._sufficient = sufficient

    async def answer(self, query: QueryRequest) -> Answer:
        return Answer(query_id=query.id, text=self._text, sufficient=self._sufficient)


@pytest.fixture
def object_store_mem() -> InMemoryObjectStore:
    return InMemoryObjectStore()


@pytest.fixture
def audit_sink() -> RecordingAuditSink:
    return RecordingAuditSink()


@pytest.fixture
def bundle() -> ContextBundle:
    return ContextBundle(id=new_id(ContextBundleId), query_id=new_id(QueryId))


@pytest.fixture
def make_runner(
    skills_root: Path,
    object_store_mem: InMemoryObjectStore,
    audit_sink: RecordingAuditSink,
    workspace: WorkspaceId,
) -> Callable[..., tuple[SkillRegistry, SkillRunner]]:
    def _make(*, secrets: dict[str, str] | None = None) -> tuple[SkillRegistry, SkillRunner]:
        registry = SkillRegistry.discover(skills_root)
        runner = SkillRunner(
            registry,
            audit_sink=audit_sink,
            object_store=object_store_mem,
            workspace_id=workspace,
            secrets=secrets or {},
        )
        return registry, runner

    return _make


@pytest.fixture
def make_loop(
    make_runner: Callable[..., tuple[SkillRegistry, SkillRunner]],
    audit_sink: RecordingAuditSink,
) -> Callable[..., AgentLoop]:
    def _make(*, text: str, sufficient: bool = True) -> AgentLoop:
        registry, runner = make_runner()
        return AgentLoop(
            answerer=FakeAnswerer(text=text, sufficient=sufficient),
            skill_runner=runner,
            registry=registry,
            audit_sink=audit_sink,
        )

    return _make


# --- testcontainers (deletion + audit-integrity integration tests) ---


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
def object_store(minio: MinioContainer) -> S3ObjectStore:
    import asyncio

    endpoint, access_key, secret_key = minio_settings(minio)
    store = S3ObjectStore(
        bucket="metis-security-test",
        endpoint_url=endpoint,
        region="us-east-1",
        access_key=access_key,
        secret_key=secret_key,
    )
    asyncio.run(store.ensure_bucket())
    return store


@pytest.fixture
async def engine(postgres: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(async_url(postgres))
    await truncate_all(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)
