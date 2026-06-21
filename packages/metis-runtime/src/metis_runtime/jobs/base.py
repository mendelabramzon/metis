"""The runtime job framework: dependency bundle, job protocol, and result type.

A runtime job is a unit of background work the worker leases by ``Job.kind`` and runs against a
shared :class:`RuntimeDeps` bundle (wired once). Unlike the gateway's inline query, these
run asynchronously on the worker; a job's result is a durable side effect (e.g. a grounded answer
filed back as a wiki-patch proposal) that surfaces through the existing review inboxes, not a value
returned to the caller — the same shape as the maintainer worker's jobs.

The engines a job uses are small protocols (``Answerer``, ``WikiProposalSink``) so a job's logic is
testable with fakes, no Postgres; :func:`build_runtime_deps` wires the real ones.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core import PostgresAuditSink
from metis_core.llm import ModelCaller
from metis_core.memory_index import EmbeddingRouter, MemoryIndexLookup, stub_router
from metis_core.stores import PostgresClaimStore
from metis_core.wiki import PostgresWikiReviewInbox
from metis_core.wiki.approval import WikiPatchReview
from metis_protocol import AuditSink, QueryRequest, WorkspaceId
from metis_runtime.query import Answer, MemoryRetriever, QueryEngine


class Answerer(Protocol):
    """Anything that turns a query into a grounded answer (the Stage 8 ``QueryEngine``)."""

    async def answer(self, query: QueryRequest) -> Answer: ...


class WikiProposalSink(Protocol):
    """A per-workspace wiki review inbox a job files a patch proposal into."""

    async def propose(self, review: WikiPatchReview) -> None: ...


@dataclass(frozen=True)
class RuntimeJobOutcome:
    """What a runtime job run produced, for the audit trail."""

    kind: str
    summary: str
    counts: Mapping[str, int] = field(default_factory=dict)


@dataclass
class RuntimeDeps:
    """Everything runtime jobs need, wired once by the worker (or a test).

    The answerer is workspace-agnostic (it scopes by the request's workspace), so it is built once
    and shared; ``wiki_inbox`` is a per-workspace factory (the review inbox is workspace-scoped).
    """

    query_engine: Answerer
    wiki_inbox: Callable[[WorkspaceId], WikiProposalSink]
    audit_sink: AuditSink


@runtime_checkable
class RuntimeJob(Protocol):
    kind: str

    async def run(self, deps: RuntimeDeps, payload: Mapping[str, Any]) -> RuntimeJobOutcome: ...


def workspace_of(payload: Mapping[str, Any]) -> WorkspaceId:
    """The workspace a job operates on (the producer always stamps it into the payload)."""
    return WorkspaceId(str(payload["workspace_id"]))


def build_runtime_deps(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    caller: ModelCaller | None = None,
    embedding_router: EmbeddingRouter | None = None,
) -> RuntimeDeps:
    """Construct the dependency bundle over a sessionmaker (the worker's wiring path).

    ``caller`` is the Stage 4 model caller the answer generator uses; ``None`` falls back to a
    deterministic extractive answer (so jobs run without a model). ``embedding_router`` defaults to
    the deterministic stub router when unset — matching the gateway's degraded retrieval path.
    """
    router = embedding_router if embedding_router is not None else stub_router()
    retriever = MemoryRetriever(MemoryIndexLookup(sessionmaker, router))
    query_engine = QueryEngine(
        retriever=retriever, claim_store=PostgresClaimStore(sessionmaker), caller=caller
    )
    return RuntimeDeps(
        query_engine=query_engine,
        wiki_inbox=lambda workspace_id: PostgresWikiReviewInbox(sessionmaker, workspace_id),
        audit_sink=PostgresAuditSink(sessionmaker),
    )
