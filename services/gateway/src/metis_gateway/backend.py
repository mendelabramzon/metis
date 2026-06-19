"""The backend the gateway orchestrates: the real engine over in-memory **or** Postgres stores.

The gateway holds no business logic — it wires the *real* Stage 9 ``SkillRunner`` and Stage 10
``AgentLoop`` and a workspace that ingests with the *real* Stage 3 ``BaselineExtractor`` (so claims
and citations are genuine). Two backends sit behind the same ``Workspace``/``AuditLog`` seams:
``build_backend`` (in-memory, no infra) and ``build_postgres_backend`` (durable — Postgres stores +
object store + the memory index, answering through the Stage 8 ``QueryEngine``). Selecting one is a
settings change, never a router change, so every router stays a thin HTTP projection.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis_core import CoreSettings, make_engine, make_sessionmaker
from metis_core.audit import PostgresAuditSink, recent_audit_events
from metis_core.llm import ModelCaller
from metis_core.memory_index import EmbeddingRouter, MemoryIndexer, MemoryIndexLookup, stub_router
from metis_core.objectstore import S3ObjectStore
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresIdentityStore,
    PostgresMemoryStore,
    PostgresMinioArtifactStore,
)
from metis_core.wiki.approval import WikiPatchReview, WikiPatchStatus
from metis_gateway.errors import ConflictError, NotFoundError
from metis_gateway.models import (
    FallbackAnswerGenerator,
    SpendTracker,
    build_embedding_router,
    build_model_plane,
)
from metis_gateway.settings import GatewaySettings
from metis_gateway.tokens import terms
from metis_ingestion import (
    BaselineExtractor,
    build_normalized_doc,
    build_raw_artifact,
    get_format,
    mime,
    parse_document,
)
from metis_ingestion.connectors import ConnectorRegistry
from metis_maintainer.memory import MemCellBuilder
from metis_protocol import (
    AgentKind,
    Attribution,
    AuditEvent,
    AuditId,
    Claim,
    ClaimRef,
    ContextBundle,
    ContextBundleId,
    ContextSection,
    IdentityStore,
    Job,
    JobId,
    JobState,
    NormalizedDoc,
    ObjectStore,
    Organization,
    PolicyState,
    QueryRequest,
    Role,
    Sensitivity,
    SourceId,
    User,
    UserId,
    WorkspaceId,
    WorkspaceMembership,
    WorkspaceModelPolicy,
    is_at_least,
    max_sensitivity,
    new_id,
)
from metis_protocol import (
    Workspace as WorkspaceEntity,
)
from metis_runtime.agent import AgentLoop
from metis_runtime.query import Answer, MemoryRetriever, QueryEngine
from metis_runtime.skills import ApprovalQueue, SkillRegistry, SkillRunner


@runtime_checkable
class Workspace(Protocol):
    """The ingest/answer/cite surface the routers use — in-memory or Postgres-backed."""

    async def ingest(
        self, *, filename: str, content: str, sensitivity: Sensitivity
    ) -> tuple[str, int]: ...

    async def answer(self, query: QueryRequest) -> Answer: ...  # the AgentLoop's Answerer

    async def citation_rows(
        self, claim_refs: Sequence[ClaimRef]
    ) -> list[tuple[str, str | None, str | None]]: ...


@runtime_checkable
class AuditLog(Protocol):
    """Append + read over the audit log (the read side backs the audit API)."""

    async def emit(self, event: AuditEvent) -> None: ...

    async def recent(self, *, action: str | None = None, limit: int = 100) -> list[AuditEvent]: ...


class InMemoryObjectStore:
    """An in-process ``ObjectStore`` for skill artifact capture (no MinIO in tests/dev)."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_bytes(self, key: str, data: bytes) -> str:
        self._objects[key] = data
        return key

    async def get_bytes(self, key: str) -> bytes | None:
        return self._objects.get(key)

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)


class RecordingAuditSink:
    """An in-process ``AuditSink`` that keeps events so the audit API can surface them."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def recent(self, *, action: str | None = None, limit: int = 100) -> list[AuditEvent]:
        chosen = [e for e in self.events if action is None or e.action == action]
        return list(reversed(chosen))[:limit]


class InMemoryIdentityStore:
    """An in-process ``IdentityStore`` for the default backend and tests (no Postgres).

    Conforms structurally to the protocol ``IdentityStore``; ``PostgresIdentityStore`` is the
    durable sibling. Writes are idempotent by id (``setdefault``), matching the durable store.
    """

    def __init__(self) -> None:
        self._orgs: dict[str, Organization] = {}
        self._users: dict[str, User] = {}
        self._workspaces: dict[str, WorkspaceEntity] = {}
        self._memberships: dict[str, WorkspaceMembership] = {}
        self._policies: dict[str, WorkspaceModelPolicy] = {}

    async def create_organization(self, org: Organization) -> Organization:
        return self._orgs.setdefault(str(org.id), org)

    async def create_user(self, user: User) -> User:
        return self._users.setdefault(str(user.id), user)

    async def create_workspace(self, workspace: WorkspaceEntity) -> WorkspaceEntity:
        return self._workspaces.setdefault(str(workspace.id), workspace)

    async def add_membership(self, membership: WorkspaceMembership) -> WorkspaceMembership:
        return self._memberships.setdefault(str(membership.id), membership)

    async def get_user(self, user_id: UserId) -> User | None:
        return self._users.get(str(user_id))

    async def get_user_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    async def get_workspace(self, workspace_id: WorkspaceId) -> WorkspaceEntity | None:
        return self._workspaces.get(str(workspace_id))

    async def resolve_role(self, *, user_id: UserId, workspace_id: WorkspaceId) -> Role | None:
        for membership in self._memberships.values():
            if membership.user_id == user_id and membership.workspace_id == workspace_id:
                return membership.role
        return None

    async def workspaces_for_user(self, user_id: UserId) -> Sequence[WorkspaceEntity]:
        ids = [m.workspace_id for m in self._memberships.values() if m.user_id == user_id]
        return [self._workspaces[str(i)] for i in ids if str(i) in self._workspaces]

    async def members_of(self, workspace_id: WorkspaceId) -> Sequence[WorkspaceMembership]:
        return [m for m in self._memberships.values() if m.workspace_id == workspace_id]

    async def get_model_policy(self, workspace_id: WorkspaceId) -> WorkspaceModelPolicy:
        return self._policies.get(
            str(workspace_id), WorkspaceModelPolicy(workspace_id=workspace_id)
        )

    async def set_model_policy(self, policy: WorkspaceModelPolicy) -> WorkspaceModelPolicy:
        self._policies[str(policy.workspace_id)] = policy
        return policy


class InMemoryWorkspace:
    """Ingests text into real claims/spans and answers by grounded lexical retrieval.

    Ingestion runs the deterministic Stage 3 extractor, so every claim cites a real source span;
    answering filters claims by the requester's sensitivity ceiling and grounds the answer in the
    matches. It is the ``Answerer`` the ``AgentLoop`` calls — citations are genuine, not stubbed.
    """

    def __init__(self, workspace_id: WorkspaceId, *, caller: ModelCaller | None = None) -> None:
        self._workspace_id = workspace_id
        self._docs: dict[str, NormalizedDoc] = {}
        self._claims: list[Claim] = []
        self._by_id: dict[str, Claim] = {}
        # With a caller wired, answers are LLM-generated over the matched evidence (cited);
        # otherwise a deterministic extractive answer.
        self._generator = FallbackAnswerGenerator(caller=caller) if caller is not None else None

    async def ingest(
        self, *, filename: str, content: str, sensitivity: Sensitivity
    ) -> tuple[str, int]:
        data = content.encode("utf-8")
        media = mime.detect(filename, data[:512])
        fmt = get_format(media.media_type)
        if fmt is None:
            raise ConflictError(f"unsupported media type {media.media_type!r}")
        policy = PolicyState(
            sensitivity=sensitivity,
            allow_external_models=not is_at_least(sensitivity, Sensitivity.RESTRICTED),
        )
        raw = build_raw_artifact(
            data,
            workspace_id=self._workspace_id,
            filename=filename,
            media_info=media,
            policy=policy,
            connector="gateway",
        )
        doc = build_normalized_doc(raw, data, policy=policy)
        parsed, segments = parse_document(doc, fmt.segmentation)
        result = BaselineExtractor().extract(doc, parsed.id, segments)

        self._docs[str(doc.id)] = doc
        for claim in result.batch.claims:
            self._claims.append(claim)
            self._by_id[str(claim.id)] = claim
        return str(doc.id), len(result.batch.claims)

    async def answer(self, query: QueryRequest) -> Answer:
        wanted = terms(query.text)
        matches = [
            claim
            for claim in self._claims
            if is_at_least(query.max_sensitivity, claim.policy.sensitivity)
            and (not wanted or wanted & terms(claim.text))
        ]
        if not matches:
            return Answer(
                query_id=query.id,
                text="I don't have enough grounded evidence in this workspace to answer that.",
                sufficient=False,
            )
        top = matches[:5]
        if self._generator is not None:  # LLM answer over the matched evidence
            bundle = ContextBundle(
                id=new_id(ContextBundleId),
                query_id=query.id,
                sections=tuple(
                    ContextSection(
                        text=claim.text,
                        claims=(ClaimRef(claim_id=claim.id),),
                        source_spans=claim.source_spans,
                    )
                    for claim in top
                ),
            )
            return await self._generator.generate(query, bundle, claims=top, sufficient=True)
        cited = top[:3]  # deterministic extractive answer (no model wired)
        text = "Based on the workspace evidence: " + " ".join(claim.text for claim in cited)
        return Answer(
            query_id=query.id,
            text=text,
            claims=tuple(ClaimRef(claim_id=claim.id) for claim in cited),
            source_spans=tuple(ref for claim in cited for ref in claim.source_spans),
            sufficient=True,
            sensitivity=max_sensitivity(*(claim.policy.sensitivity for claim in cited)),
        )

    async def citation_rows(
        self, claim_refs: Sequence[ClaimRef]
    ) -> list[tuple[str, str | None, str | None]]:
        """Resolve claim refs back to (claim_id, source_span_id, artifact_id) for the API."""
        rows: list[tuple[str, str | None, str | None]] = []
        for ref in claim_refs:
            claim = self._by_id.get(str(ref.claim_id))
            span = claim.source_spans[0] if claim and claim.source_spans else None
            rows.append(
                (
                    str(ref.claim_id),
                    str(span.source_span_id) if span else None,
                    str(span.artifact_id) if span else None,
                )
            )
        return rows


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    connector: str
    sensitivity: Sensitivity
    auth_method: str


class SourceRegistry:
    """Configured sources, validated against the Stage 11 connector registry."""

    def __init__(self, connectors: ConnectorRegistry) -> None:
        self._connectors = connectors
        self._sources: dict[str, SourceConfig] = {}

    def register(self, *, name: str, connector: str, sensitivity: Sensitivity) -> SourceConfig:
        spec = self._connectors.get(connector)
        if spec is None:
            raise ConflictError(f"unknown connector {connector!r}")
        config = SourceConfig(
            id=new_id(SourceId),
            name=name,
            connector=connector,
            sensitivity=sensitivity,
            auth_method=spec.auth.method.value,
        )
        self._sources[config.id] = config
        return config

    def list(self) -> list[SourceConfig]:
        return list(self._sources.values())

    def get(self, source_id: str) -> SourceConfig:
        config = self._sources.get(source_id)
        if config is None:
            raise NotFoundError(f"no source {source_id!r}")
        return config


class WikiInbox:
    """In-memory wiki patch reviews (the Stage 7 state machine; durable store is later)."""

    def __init__(self) -> None:
        self._reviews: dict[str, WikiPatchReview] = {}

    def propose(self, review: WikiPatchReview) -> None:
        self._reviews[str(review.patch.id)] = review

    def pending(self) -> list[WikiPatchReview]:
        return [r for r in self._reviews.values() if r.status is WikiPatchStatus.PROPOSED]

    def approve(self, patch_id: str, *, note: str) -> WikiPatchReview:
        review = self._reviews.get(patch_id)
        if review is None:
            raise NotFoundError(f"no wiki patch {patch_id!r}")
        approved = review.approve(note=note)
        self._reviews[patch_id] = approved
        return approved


class InMemoryJobQueue:
    """A ``JobQueue`` plus the inspect/retry surface the ops API needs (durable queue is later)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._errors: dict[str, str] = {}

    async def enqueue(self, job: Job) -> JobId:
        self._jobs[str(job.id)] = job
        return job.id

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]:
        leased = [j for j in self._jobs.values() if j.kind in kinds and j.state is JobState.PENDING]
        return leased[:limit]

    async def complete(self, job_id: JobId) -> None:
        self._set_state(str(job_id), JobState.SUCCEEDED)

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None:
        self._errors[str(job_id)] = error
        self._set_state(str(job_id), JobState.RETRYING if retry else JobState.FAILED)

    def list(self) -> list[Job]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"no job {job_id!r}")
        return job

    def error_for(self, job_id: str) -> str | None:
        return self._errors.get(job_id)

    def retry(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.state not in (JobState.FAILED, JobState.RETRYING):
            raise ConflictError(f"job {job_id!r} is {job.state.value}, not retryable")
        self._errors.pop(job_id, None)
        revived = job.model_copy(update={"state": JobState.PENDING, "attempts": job.attempts + 1})
        self._jobs[job_id] = revived
        return revived

    def _set_state(self, job_id: str, state: JobState) -> None:
        job = self.get(job_id)
        self._jobs[job_id] = job.model_copy(update={"state": state})


@dataclass(frozen=True)
class InboxItem:
    kind: str  # "action" | "wiki_patch"
    id: str
    summary: str
    status: str


def _patch_summary(review: WikiPatchReview) -> str:
    patch = review.patch
    return patch.title or patch.rationale or str(patch.id)


class ApprovalInbox:
    """One queue over two approval sources: agent/skill actions and wiki patches.

    Reviewers see a single list; approving dispatches to the right state machine and *always* emits
    an ``approval.granted`` audit event, so a human decision is explicit and on the record.
    """

    def __init__(
        self,
        approvals: ApprovalQueue,
        wiki: WikiInbox,
        audit: AuditLog,
        workspace_id: WorkspaceId,
    ) -> None:
        self._approvals = approvals
        self._wiki = wiki
        self._audit = audit
        self._workspace_id = workspace_id

    def pending(self) -> list[InboxItem]:
        items = [
            InboxItem("action", r.key, f"{r.skill_name}@{r.skill_version}", r.status.value)
            for r in self._approvals.pending()
        ]
        items += [
            InboxItem("wiki_patch", str(r.patch.id), _patch_summary(r), r.status.value)
            for r in self._wiki.pending()
        ]
        return items

    async def approve(self, *, kind: str, item_id: str, note: str) -> InboxItem:
        if kind == "action":
            keys = {r.key for r in self._approvals.pending()}
            if item_id not in keys:
                raise NotFoundError(f"no pending action {item_id!r}")
            self._approvals.approve(item_id)
            await self._record("SkillAction", item_id, note)
            return InboxItem("action", item_id, item_id, "approved")
        if kind == "wiki_patch":
            review = self._wiki.approve(item_id, note=note)
            await self._record("WikiPatch", item_id, note)
            return InboxItem("wiki_patch", item_id, _patch_summary(review), review.status.value)
        raise NotFoundError(f"unknown approval kind {kind!r}")

    async def _record(self, target_kind: str, target_id: str, note: str) -> None:
        await self._audit.emit(
            AuditEvent(
                id=new_id(AuditId),
                workspace_id=self._workspace_id,
                occurred_at=datetime.now(UTC),
                actor=Attribution(agent_kind=AgentKind.HUMAN, agent="operator"),
                action="approval.granted",
                target_id=target_id,
                target_kind=target_kind,
                payload={"note": note} if note else None,
            )
        )


class PostgresWorkspace:
    """Durable workspace: ingests into Postgres + the memory index, answers via the Stage 8 engine.

    Ingestion persists raw/normalized/parsed/segments/claims to the real stores, then consolidates
    the claims into an indexed ``MemCell`` so the ``QueryEngine``'s hybrid memory retrieval can find
    it. Answering and citation resolution go through the real engine + claim store, so the data
    survives a restart — unlike the in-memory workspace.
    """

    def __init__(
        self,
        *,
        workspace_id: WorkspaceId,
        sessionmaker: async_sessionmaker[AsyncSession],
        object_store: S3ObjectStore,
        query_engine: QueryEngine,
        embedding_router: EmbeddingRouter,
    ) -> None:
        self._workspace_id = workspace_id
        self._artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
        self._documents = PostgresDocumentStore(sessionmaker)
        self._claims = PostgresClaimStore(sessionmaker)
        self._memory = PostgresMemoryStore(sessionmaker)
        # Index with the same embedder the query engine retrieves with, so vectors are comparable.
        self._indexer = MemoryIndexer(sessionmaker, embedding_router)
        self._builder = MemCellBuilder()  # deterministic, evidence-only (no model call)
        self._query = query_engine

    async def ingest(
        self, *, filename: str, content: str, sensitivity: Sensitivity
    ) -> tuple[str, int]:
        data = content.encode("utf-8")
        media = mime.detect(filename, data[:512])
        fmt = get_format(media.media_type)
        if fmt is None:
            raise ConflictError(f"unsupported media type {media.media_type!r}")
        policy = PolicyState(
            sensitivity=sensitivity,
            allow_external_models=not is_at_least(sensitivity, Sensitivity.RESTRICTED),
        )
        raw = build_raw_artifact(
            data,
            workspace_id=self._workspace_id,
            filename=filename,
            media_info=media,
            policy=policy,
            connector="gateway",
        )
        await self._artifacts.put_blob(data)
        await self._artifacts.put(raw)
        doc = build_normalized_doc(raw, data, policy=policy)
        await self._documents.put_normalized(doc)
        parsed, segments = parse_document(doc, fmt.segmentation)
        await self._documents.put_parsed(parsed)
        await self._documents.put_segments(segments)
        result = BaselineExtractor().extract(doc, parsed.id, segments)
        await self._documents.put_source_spans(str(self._workspace_id), result.source_spans)
        await self._claims.write(result.batch)
        if result.batch.claims:  # consolidate -> index so retrieval can find it
            cell = await self._builder.build(
                workspace_id=self._workspace_id, claims=result.batch.claims
            )
            await self._memory.write_mem_cell(cell)
            await self._indexer.index_mem_cell(cell)
        return str(doc.id), len(result.batch.claims)

    async def answer(self, query: QueryRequest) -> Answer:
        return await self._query.answer(query)

    async def citation_rows(
        self, claim_refs: Sequence[ClaimRef]
    ) -> list[tuple[str, str | None, str | None]]:
        rows: list[tuple[str, str | None, str | None]] = []
        for ref in claim_refs:
            claim = await self._claims.get(ref.claim_id)
            span = claim.source_spans[0] if claim and claim.source_spans else None
            rows.append(
                (
                    str(ref.claim_id),
                    str(span.source_span_id) if span else None,
                    str(span.artifact_id) if span else None,
                )
            )
        return rows


class PostgresAuditLog:
    """Durable audit: appends via the hash-chained sink, reads via ``recent_audit_events``."""

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], workspace_id: WorkspaceId
    ) -> None:
        self._sink = PostgresAuditSink(sessionmaker)
        self._sessionmaker = sessionmaker
        self._workspace_id = workspace_id

    async def emit(self, event: AuditEvent) -> None:
        await self._sink.emit(event)

    async def recent(self, *, action: str | None = None, limit: int = 100) -> list[AuditEvent]:
        return await recent_audit_events(
            self._sessionmaker, workspace_id=str(self._workspace_id), action=action, limit=limit
        )


@dataclass
class Backend:
    """Everything the routers depend on, wired once at app assembly (memory or Postgres)."""

    workspace_id: WorkspaceId
    workspace: Workspace
    agent: AgentLoop
    skills: SkillRegistry
    skill_runner: SkillRunner
    jobs: InMemoryJobQueue
    audit: AuditLog
    sources: SourceRegistry
    wiki: WikiInbox
    inbox: ApprovalInbox
    identity: IdentityStore = field(default_factory=InMemoryIdentityStore)
    object_store: ObjectStore = field(default_factory=InMemoryObjectStore)
    engine: AsyncEngine | None = None  # set for the Postgres backend; disposed at shutdown
    http_client: httpx.AsyncClient | None = (
        None  # the local model client (chat + embeddings); closed at shutdown
    )
    model_closers: tuple[Callable[[], Awaitable[None]], ...] = ()  # cloud clients to close
    spend: SpendTracker | None = None  # per-workspace model spend (None when no model is wired)
    # Builds a per-workspace engine for (workspace_id, allow_external) on demand (set by the build
    # functions); ``workspace``/``agent`` above are the configured workspace's default engine.
    workspace_factory: Callable[[WorkspaceId, bool], Workspace] | None = None
    _workspaces: dict[tuple[str, bool], Workspace] = field(default_factory=dict, repr=False)
    _agents: dict[tuple[str, bool], AgentLoop] = field(default_factory=dict, repr=False)

    def workspace_for(self, workspace_id: WorkspaceId, *, allow_external: bool = True) -> Workspace:
        """The ingest/answer engine for ``workspace_id`` under its model policy — the configured
        default one, or built on demand and cached. The membership gate runs before this is reached,
        so the caller is always a member of the workspace it returns."""
        if str(workspace_id) == str(self.workspace_id) and allow_external:
            return self.workspace
        if self.workspace_factory is None:
            raise NotFoundError(f"workspace {workspace_id} is not served by this backend")
        key = (str(workspace_id), allow_external)
        engine = self._workspaces.get(key)
        if engine is None:
            engine = self.workspace_factory(workspace_id, allow_external)
            self._workspaces[key] = engine
        return engine

    def agent_for(self, workspace_id: WorkspaceId, *, allow_external: bool = True) -> AgentLoop:
        """The agent loop for ``workspace_id`` under its model policy — cached so a run held for
        approval persists from the request that proposes it to the one that resumes it (a policy
        change between those is the rare case that drops the held run)."""
        if str(workspace_id) == str(self.workspace_id) and allow_external:
            return self.agent
        key = (str(workspace_id), allow_external)
        agent = self._agents.get(key)
        if agent is None:
            agent = AgentLoop(
                answerer=self.workspace_for(workspace_id, allow_external=allow_external),
                skill_runner=self.skill_runner,
                registry=self.skills,
                audit_sink=self.audit,
            )
            self._agents[key] = agent
        return agent


def build_backend(settings: GatewaySettings) -> Backend:
    """Assemble the in-memory backend from settings (the swap point for durable wiring)."""
    workspace_id = WorkspaceId(settings.workspace_id)
    audit = RecordingAuditSink()
    object_store = InMemoryObjectStore()

    plane = build_model_plane(settings, audit_sink=audit)

    skills = (
        SkillRegistry.discover(Path(settings.skills_root))
        if settings.skills_root
        else SkillRegistry()
    )
    skill_runner = SkillRunner(
        skills, audit_sink=audit, object_store=object_store, workspace_id=workspace_id
    )

    def _workspace_factory(ws_id: WorkspaceId, allow_external: bool) -> Workspace:
        return InMemoryWorkspace(ws_id, caller=plane.make_caller(allow_external=allow_external))

    workspace = _workspace_factory(workspace_id, allow_external=True)
    agent = AgentLoop(
        answerer=workspace, skill_runner=skill_runner, registry=skills, audit_sink=audit
    )
    wiki = WikiInbox()
    inbox = ApprovalInbox(skill_runner.approvals, wiki, audit, workspace_id)

    return Backend(
        workspace_id=workspace_id,
        workspace=workspace,
        agent=agent,
        skills=skills,
        skill_runner=skill_runner,
        jobs=InMemoryJobQueue(),
        audit=audit,
        sources=SourceRegistry(ConnectorRegistry.with_defaults()),
        wiki=wiki,
        inbox=inbox,
        object_store=object_store,
        http_client=plane.local_client,
        model_closers=plane.closers,
        spend=plane.spend,
        workspace_factory=_workspace_factory,
    )


async def build_postgres_backend(settings: GatewaySettings) -> Backend:
    """Assemble the durable backend: Postgres stores + object store + memory index + query engine.

    DB/object-store config comes from the core settings (``METIS_CORE_*``); the engine is returned
    on the ``Backend`` so the app can dispose it at shutdown.
    """
    core = CoreSettings()
    workspace_id = WorkspaceId(settings.workspace_id)

    engine = make_engine(core.database_url)
    sessionmaker = make_sessionmaker(engine)
    object_store = S3ObjectStore(
        bucket=core.object_store_bucket,
        endpoint_url=core.object_store_endpoint_url,
        region=core.object_store_region,
        access_key=core.object_store_access_key,
        secret_key=core.object_store_secret_key,
    )
    await object_store.ensure_bucket()

    audit = PostgresAuditLog(sessionmaker, workspace_id)

    # Model wiring (optional). Chat: Anthropic/OpenAI-compatible cloud + local fallback assembled by
    # the plane. Embeddings: local bge-m3 when an endpoint is set, else stub vectors. The answer
    # generator degrades to extractive on a model error.
    plane = build_model_plane(settings, audit_sink=audit)
    if plane.local_client is not None and settings.model_endpoint is not None:
        embedding_router: EmbeddingRouter = build_embedding_router(
            plane.local_client, endpoint=settings.model_endpoint, model=settings.embedding_model
        )
    else:
        embedding_router = stub_router()

    # Retriever + claim store are workspace-agnostic (they scope by the request's workspace_id), so
    # they are built once and shared; only the answer generator's caller varies with the workspace's
    # model policy, so the query engine is assembled per (workspace, allow_external) in the factory.
    retriever = MemoryRetriever(MemoryIndexLookup(sessionmaker, embedding_router))
    claim_store = PostgresClaimStore(sessionmaker)

    def _workspace_factory(ws_id: WorkspaceId, allow_external: bool) -> Workspace:
        caller = plane.make_caller(allow_external=allow_external)
        query_engine = QueryEngine(
            retriever=retriever,
            claim_store=claim_store,
            generator=FallbackAnswerGenerator(caller=caller) if caller is not None else None,
        )
        return PostgresWorkspace(
            workspace_id=ws_id,
            sessionmaker=sessionmaker,
            object_store=object_store,
            query_engine=query_engine,
            embedding_router=embedding_router,
        )

    workspace = _workspace_factory(workspace_id, allow_external=True)
    skills = (
        SkillRegistry.discover(Path(settings.skills_root))
        if settings.skills_root
        else SkillRegistry()
    )
    skill_runner = SkillRunner(
        skills, audit_sink=audit, object_store=object_store, workspace_id=workspace_id
    )
    agent = AgentLoop(
        answerer=workspace, skill_runner=skill_runner, registry=skills, audit_sink=audit
    )
    wiki = WikiInbox()
    inbox = ApprovalInbox(skill_runner.approvals, wiki, audit, workspace_id)

    return Backend(
        workspace_id=workspace_id,
        workspace=workspace,
        agent=agent,
        skills=skills,
        skill_runner=skill_runner,
        jobs=InMemoryJobQueue(),  # jobs originate in the workers (their loops are a follow-up)
        audit=audit,
        sources=SourceRegistry(ConnectorRegistry.with_defaults()),
        wiki=wiki,
        inbox=inbox,
        identity=PostgresIdentityStore(sessionmaker),
        object_store=object_store,
        engine=engine,
        http_client=plane.local_client,
        model_closers=plane.closers,
        spend=plane.spend,
        workspace_factory=_workspace_factory,
    )
