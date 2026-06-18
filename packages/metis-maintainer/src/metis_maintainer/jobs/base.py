"""The maintainer job framework: dependency bundle, job protocol, and result type.

A maintainer job is a small unit declaring its ``kind`` (the queue ``Job.kind``), which
``triggers`` fire it (event-driven and/or periodic), and an ``idempotency_key`` derived from
its payload. The scheduler turns ``(kind, workspace, key)`` into a deterministic job id so
enqueuing the same unit of work twice is a no-op; jobs additionally make their *effects*
idempotent by writing memory objects with deterministic ids (Stage 5). Jobs run against a
:class:`MaintainerDeps` bundle, which the worker builds once.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core import PostgresAuditSink
from metis_core.llm import ModelCaller
from metis_core.memory_index import MemoryIndexer
from metis_core.stores import (
    PostgresClaimStore,
    PostgresMemoryStore,
    PostgresWikiStore,
)
from metis_maintainer.memory import (
    ForesightBuilder,
    MemCellBuilder,
    ProfileBuilder,
    SceneBuilder,
)
from metis_protocol import AuditSink, ClaimStore, MemoryStore, WikiStore, WorkspaceId


class Trigger(StrEnum):
    """When a job runs: in response to an event, on a cadence, or both."""

    EVENT = "event"
    PERIODIC = "periodic"


@dataclass(frozen=True)
class JobOutcome:
    """What a job run produced, for the maintenance audit trail."""

    kind: str
    summary: str
    counts: Mapping[str, int] = field(default_factory=dict)


@dataclass
class MaintainerDeps:
    """Everything jobs need, wired once by the worker (or a test)."""

    sessionmaker: async_sessionmaker[AsyncSession]
    memory_store: MemoryStore
    claim_store: ClaimStore
    wiki_store: WikiStore
    audit_sink: AuditSink
    memcell_builder: MemCellBuilder
    scene_builder: SceneBuilder
    profile_builder: ProfileBuilder
    foresight_builder: ForesightBuilder
    indexer: MemoryIndexer | None = None  # re-index refreshed scenes when available


@runtime_checkable
class MaintainerJob(Protocol):
    kind: str
    triggers: tuple[Trigger, ...]

    def idempotency_key(self, payload: Mapping[str, Any]) -> str: ...

    async def run(self, deps: MaintainerDeps, payload: Mapping[str, Any]) -> JobOutcome: ...


def workspace_of(payload: Mapping[str, Any]) -> WorkspaceId:
    """The workspace a job operates on (the scheduler always stamps it into the payload)."""
    return WorkspaceId(str(payload["workspace_id"]))


def build_deps(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    caller: ModelCaller | None = None,
    indexer: MemoryIndexer | None = None,
) -> MaintainerDeps:
    """Construct the dependency bundle over a sessionmaker (the worker's wiring path).

    ``caller`` is the Stage 4 model caller used by the LLM-backed builders; when ``None`` the
    builders fall back to deterministic, evidence-only summaries (so jobs run without a model).
    """
    return MaintainerDeps(
        sessionmaker=sessionmaker,
        memory_store=PostgresMemoryStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        wiki_store=PostgresWikiStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
        memcell_builder=MemCellBuilder(caller=caller),
        scene_builder=SceneBuilder(caller=caller),
        profile_builder=ProfileBuilder(),
        foresight_builder=ForesightBuilder(caller=caller),
        indexer=indexer,
    )
