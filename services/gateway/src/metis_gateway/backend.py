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
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis_core import CoreSettings, make_engine, make_sessionmaker
from metis_core.audit import PostgresAuditSink, recent_audit_events
from metis_core.db.session import unit_of_work
from metis_core.jobs import PostgresJobQueue
from metis_core.llm import ModelCaller
from metis_core.llm.ocr import model_transcriber
from metis_core.memory_index import EmbeddingRouter, MemoryIndexer, MemoryIndexLookup
from metis_core.models import RawArtifactRow, SkillApprovalRow
from metis_core.objectstore import S3ObjectStore
from metis_core.security import Cryptobox
from metis_core.security.deletion import ErasureResult, ErasureSummary
from metis_core.security.deletion import erase_artifact as erase_artifact_core
from metis_core.security.deletion import erase_source as erase_source_core
from metis_core.security.deletion import erase_workspace_artifacts as erase_workspace_artifacts_core
from metis_core.stores import (
    PostgresActionStore,
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresIdentityStore,
    PostgresMemoryStore,
    PostgresMinioArtifactStore,
    PostgresSourceStore,
)
from metis_core.tombstone import TombstoneResult
from metis_core.wiki import PostgresWikiReviewInbox
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
    assess,
    build_normalized_doc_rich,
    build_raw_artifact,
    get_format,
    mime,
    parse_document,
)
from metis_ingestion.connectors import ConnectorRegistry
from metis_ingestion.parsers.ocr import Transcribe
from metis_ingestion.security.cred_store import EncryptedCredentialStore
from metis_maintainer.memory import MemCellBuilder
from metis_protocol import (
    ActionId,
    ActionStatus,
    ActionStore,
    AgentKind,
    ArtifactId,
    ArtifactRef,
    Attribution,
    AuditEvent,
    AuditId,
    Claim,
    ClaimId,
    ClaimRef,
    ConnectorRun,
    ContextBundle,
    ContextBundleId,
    ContextSection,
    Contradiction,
    ContradictionId,
    ContradictionStatus,
    IdentityStore,
    Job,
    JobId,
    JobState,
    MemCell,
    MemCellId,
    MemoryOp,
    MemoryPatch,
    MemoryPatchId,
    MemoryScope,
    ModelCapability,
    NormalizedDoc,
    ObjectStore,
    Organization,
    PolicyState,
    ProposedAction,
    Provenance,
    QueryRequest,
    RawArtifact,
    Role,
    Sensitivity,
    SkillInput,
    SourceConfig,
    SourceCursor,
    SourceId,
    SourceSpan,
    SourceSpanRef,
    SourceStore,
    TelegramDiscoveredChat,
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
from metis_runtime.skills import (
    ApprovalQueue,
    ApprovalRequest,
    SkillApprovalStatus,
    SkillRegistry,
    SkillRunner,
    approval_key,
)


@dataclass(frozen=True)
class IngestOutcome:
    """The parse-status projection of one ingested file: enough for the upload UI to show what
    happened (the detected type, segment/claim counts, and the parse-quality report)."""

    doc_id: str
    media_type: str
    segments: int
    claims: int
    coverage: float = 1.0
    page_count: int | None = None
    tables: int = 0
    warnings: tuple[str, ...] = ()
    parse_path: str = "deterministic"


# --- evidence drill-down (the evidence browser reads these) ------------------------------------


@dataclass(frozen=True)
class SpanEvidence:
    """One source span behind a claim: where it points, and the exact quoted text."""

    source_span_id: str
    artifact_id: str
    doc_id: str | None
    char_start: int
    char_end: int
    page: int | None
    quote: str | None  # NormalizedDoc.text[char_start:char_end], when the doc is resolvable


@dataclass(frozen=True)
class ClaimEvidence:
    """A claim with its supporting spans expanded — the 'why this claim' trail."""

    claim_id: str
    text: str
    confidence: float
    negated: bool
    sensitivity: str
    spans: tuple[SpanEvidence, ...]


@dataclass(frozen=True)
class ArtifactEvidence:
    """A raw artifact's metadata — the source a span points back to."""

    artifact_id: str
    filename: str | None
    media_type: str
    byte_size: int
    kind: str
    connector: str
    source_id: str | None
    created_at: datetime
    tombstoned: bool


@dataclass(frozen=True)
class MemCellEvidence:
    """A consolidated memory cell and the claims it rests on."""

    mem_cell_id: str
    summary: str
    sensitivity: str
    claim_ids: tuple[str, ...]


def _artifact_evidence(raw: RawArtifact) -> ArtifactEvidence:
    return ArtifactEvidence(
        artifact_id=str(raw.id),
        filename=raw.filename,
        media_type=raw.media_type,
        byte_size=raw.byte_size,
        kind=raw.kind.value,
        connector=raw.provenance.attribution.agent,
        source_id=str(raw.source_id) if raw.source_id is not None else None,
        created_at=raw.created_at,
        tombstoned=raw.tombstoned_at is not None,
    )


@runtime_checkable
class Workspace(Protocol):
    """The ingest/answer/cite surface the routers use — in-memory or Postgres-backed."""

    async def ingest_bytes(
        self, *, filename: str, data: bytes, sensitivity: Sensitivity, connector: str = "upload"
    ) -> IngestOutcome: ...

    async def ingest(
        self, *, filename: str, content: str, sensitivity: Sensitivity
    ) -> tuple[str, int]: ...

    async def answer(self, query: QueryRequest) -> Answer: ...  # the AgentLoop's Answerer

    async def citation_rows(
        self, claim_refs: Sequence[ClaimRef]
    ) -> list[tuple[str, str | None, str | None]]: ...

    # Returns None when no such artifact exists *in this workspace* (the isolation guard → 404).
    async def erase_artifact(self, artifact_id: str) -> ErasureResult | None: ...

    async def erase_source(self, source_id: str) -> ErasureSummary: ...

    # Erase every artifact this source produced in this workspace (empty on the in-memory backend,
    # which does not track source provenance).

    async def erase_workspace_artifacts(self) -> ErasureSummary: ...

    # Erase every artifact in this workspace (purges a user's personal workspace on erasure).

    # Evidence drill-down — each returns None when the entity is not in this workspace (→ 404).
    async def claim_evidence(self, claim_id: str) -> ClaimEvidence | None: ...

    async def artifact_evidence(self, artifact_id: str) -> ArtifactEvidence | None: ...

    async def mem_cell_evidence(self, mem_cell_id: str) -> MemCellEvidence | None: ...

    # Contradiction inbox — conflicting evidence for review (empty in-memory; the maintainer
    # detects and persists these on the durable backend).
    async def list_contradictions(
        self, *, status: ContradictionStatus | None
    ) -> Sequence[Contradiction]: ...

    async def resolve_contradiction(
        self, contradiction_id: str, *, status: ContradictionStatus
    ) -> Contradiction | None: ...

    # Memory review — the write/manage/read loop over consolidated memory (empty in-memory).
    async def list_memory(self) -> Sequence[MemCell]: ...

    async def revise_mem_cell(
        self, mem_cell_id: str, *, op: MemoryOp, reason: str, actor: str
    ) -> MemCell | None: ...


@runtime_checkable
class AuditLog(Protocol):
    """Append + read over the audit log (the read side backs the audit API)."""

    async def emit(self, event: AuditEvent) -> None: ...

    async def recent(self, *, action: str | None = None, limit: int = 100) -> list[AuditEvent]: ...


@runtime_checkable
class JobOps(Protocol):
    """The job queue + the operator inspect/retry surface — in-memory or Postgres-backed."""

    async def enqueue(self, job: Job) -> JobId: ...

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]: ...

    async def complete(self, job_id: JobId) -> None: ...

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None: ...

    async def list(self, workspace_id: WorkspaceId) -> Sequence[Job]: ...

    async def get(self, job_id: JobId) -> Job | None: ...

    async def error_for(self, job_id: JobId) -> str | None: ...

    async def retry(self, job_id: JobId) -> Job | None: ...


@runtime_checkable
class WikiReviewInbox(Protocol):
    """The wiki patch approval queue — in-memory or Postgres-backed."""

    async def propose(self, review: WikiPatchReview) -> None: ...

    async def pending(self) -> Sequence[WikiPatchReview]: ...

    async def approve(self, patch_id: str, *, note: str) -> WikiPatchReview | None: ...


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

    async def deactivate_user(self, user_id: UserId) -> User | None:
        user = self._users.get(str(user_id))
        if user is None:
            return None
        deactivated = user.model_copy(update={"active": False})
        self._users[str(user_id)] = deactivated
        return deactivated


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
        self._artifacts: dict[str, str] = {}  # artifact_id -> doc_id, so erasure can find the doc
        self._raw: dict[str, RawArtifact] = {}  # artifact_id -> raw, for evidence drill-down
        self._spans: dict[str, SourceSpan] = {}  # span_id -> span, to resolve a claim's quotes
        # With a caller wired, answers are LLM-generated over the matched evidence (cited);
        # otherwise a deterministic extractive answer.
        self._generator = FallbackAnswerGenerator(caller=caller) if caller is not None else None

    async def ingest_bytes(
        self, *, filename: str, data: bytes, sensitivity: Sensitivity, connector: str = "upload"
    ) -> IngestOutcome:
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
            connector=connector,
        )
        doc, product = await build_normalized_doc_rich(raw, data, policy=policy)
        parsed, segments = parse_document(
            doc, fmt.segmentation, pages=product.pages, page_count=product.page_count
        )
        result = BaselineExtractor().extract(doc, parsed.id, segments)
        quality = assess(product, segments=len(segments))

        self._docs[str(doc.id)] = doc
        self._artifacts[str(raw.id)] = str(doc.id)
        self._raw[str(raw.id)] = raw
        for span in result.source_spans:
            self._spans[str(span.id)] = span
        for claim in result.batch.claims:
            self._claims.append(claim)
            self._by_id[str(claim.id)] = claim
        return IngestOutcome(
            doc_id=str(doc.id),
            media_type=media.media_type,
            segments=len(segments),
            claims=len(result.batch.claims),
            coverage=quality.coverage,
            page_count=quality.page_count,
            tables=quality.tables,
            warnings=quality.warnings,
            parse_path=product.parse_path,
        )

    async def ingest(
        self, *, filename: str, content: str, sensitivity: Sensitivity
    ) -> tuple[str, int]:
        outcome = await self.ingest_bytes(
            filename=filename,
            data=content.encode("utf-8"),
            sensitivity=sensitivity,
            connector="gateway",
        )
        return outcome.doc_id, outcome.claims

    async def erase_artifact(self, artifact_id: str) -> ErasureResult | None:
        """Best-effort erasure for the in-memory backend: drop the artifact's doc and the claims
        citing it. There is no object store or row graph here, so the counts cover what is held;
        the durable backend (``PostgresWorkspace``) runs the full tombstone cascade + blob erase."""
        doc_id = self._artifacts.pop(artifact_id, None)
        if doc_id is None:
            return None
        self._docs.pop(doc_id, None)
        self._raw.pop(artifact_id, None)
        for span_id in [sid for sid, s in self._spans.items() if str(s.artifact_id) == artifact_id]:
            self._spans.pop(span_id, None)
        erased = [
            claim
            for claim in self._claims
            if any(str(span.artifact_id) == artifact_id for span in claim.source_spans)
        ]
        for claim in erased:
            self._claims.remove(claim)
            self._by_id.pop(str(claim.id), None)
        return ErasureResult(
            tombstoned=TombstoneResult(
                raw_artifacts=1,
                normalized_docs=1,
                parsed_docs=0,
                segments=0,
                claims=len(erased),
                mem_cells=0,
            ),
            blobs_erased=0,
        )

    async def erase_source(self, source_id: str) -> ErasureSummary:
        """The in-memory backend does not record source provenance on its artifacts (inline ingest
        has no source), so there is nothing to enumerate; the durable backend does the real work."""
        return ErasureSummary(artifacts=0, claims=0, mem_cells=0, blobs_erased=0)

    async def erase_workspace_artifacts(self) -> ErasureSummary:
        """Erase every artifact held in this workspace (drops each doc and the claims citing it)."""
        artifacts = claims = 0
        for artifact_id in list(self._artifacts):
            result = await self.erase_artifact(artifact_id)
            if result is not None:
                artifacts += result.tombstoned.raw_artifacts
                claims += result.tombstoned.claims
        return ErasureSummary(artifacts=artifacts, claims=claims, mem_cells=0, blobs_erased=0)

    async def claim_evidence(self, claim_id: str) -> ClaimEvidence | None:
        claim = self._by_id.get(claim_id)
        if claim is None:
            return None
        return ClaimEvidence(
            claim_id=claim_id,
            text=claim.text,
            confidence=claim.confidence,
            negated=claim.negated,
            sensitivity=claim.policy.sensitivity.value,
            spans=tuple(self._span_evidence(ref) for ref in claim.source_spans),
        )

    def _span_evidence(self, ref: SourceSpanRef) -> SpanEvidence:
        span = self._spans.get(str(ref.source_span_id))
        quote: str | None = None
        if span is not None and span.doc_id is not None:
            doc = self._docs.get(str(span.doc_id))
            if doc is not None:
                quote = doc.text[span.char_start : span.char_end]
        return SpanEvidence(
            source_span_id=str(ref.source_span_id),
            artifact_id=str(ref.artifact_id),
            doc_id=str(ref.doc_id) if ref.doc_id is not None else None,
            char_start=span.char_start if span is not None else 0,
            char_end=span.char_end if span is not None else 0,
            page=span.page if span is not None else None,
            quote=quote,
        )

    async def artifact_evidence(self, artifact_id: str) -> ArtifactEvidence | None:
        raw = self._raw.get(artifact_id)
        return _artifact_evidence(raw) if raw is not None else None

    async def mem_cell_evidence(self, mem_cell_id: str) -> MemCellEvidence | None:
        return None  # the in-memory backend builds no mem cells

    async def list_contradictions(
        self, *, status: ContradictionStatus | None
    ) -> Sequence[Contradiction]:
        return ()  # the in-memory backend detects no contradictions

    async def resolve_contradiction(
        self, contradiction_id: str, *, status: ContradictionStatus
    ) -> Contradiction | None:
        return None

    async def list_memory(self) -> Sequence[MemCell]:
        return ()  # the in-memory backend builds no consolidated memory cells

    async def revise_mem_cell(
        self, mem_cell_id: str, *, op: MemoryOp, reason: str, actor: str
    ) -> MemCell | None:
        return None

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


class InMemorySourceStore:
    """An in-process ``SourceStore`` for the default backend and tests (no Postgres).

    Conforms structurally to the protocol ``SourceStore``; ``PostgresSourceStore`` is the durable
    sibling. Writes are idempotent by id (config) / upsert by key (cursor, run), matching it.
    """

    def __init__(self) -> None:
        self._configs: dict[str, SourceConfig] = {}
        self._cursors: dict[str, SourceCursor] = {}
        self._runs: dict[str, ConnectorRun] = {}
        self._chats: dict[tuple[str, int], TelegramDiscoveredChat] = {}

    async def register(self, config: SourceConfig) -> SourceConfig:
        return self._configs.setdefault(str(config.id), config)

    async def get(self, source_id: SourceId) -> SourceConfig | None:
        return self._configs.get(str(source_id))

    async def list(self, workspace_id: WorkspaceId) -> Sequence[SourceConfig]:
        return [c for c in self._configs.values() if c.workspace_id == workspace_id]

    async def list_all(self) -> Sequence[SourceConfig]:
        return list(self._configs.values())

    async def get_cursor(self, source_id: SourceId) -> SourceCursor | None:
        return self._cursors.get(str(source_id))

    async def set_cursor(self, cursor: SourceCursor) -> SourceCursor:
        self._cursors[str(cursor.source_id)] = cursor
        return cursor

    async def record_run(self, run: ConnectorRun) -> ConnectorRun:
        self._runs[str(run.id)] = run
        return run

    async def runs_for(self, source_id: SourceId, *, limit: int = 50) -> Sequence[ConnectorRun]:
        runs = [r for r in self._runs.values() if r.source_id == source_id]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    async def delete(self, source_id: SourceId) -> None:
        sid = str(source_id)
        self._configs.pop(sid, None)
        self._cursors.pop(sid, None)
        self._runs = {k: v for k, v in self._runs.items() if str(v.source_id) != sid}

    async def upsert_discovered_chat(self, chat: TelegramDiscoveredChat) -> TelegramDiscoveredChat:
        self._chats[(chat.business_connection_id, chat.chat_id)] = chat
        return chat

    async def list_discovered_chats(
        self, business_connection_id: str | None = None
    ) -> Sequence[TelegramDiscoveredChat]:
        chats = [
            c
            for c in self._chats.values()
            if business_connection_id is None or c.business_connection_id == business_connection_id
        ]
        chats.sort(key=lambda c: c.last_seen_at, reverse=True)
        return chats


class InMemoryActionStore:
    """In-process ``ActionStore`` for the default backend and tests (durable: Postgres)."""

    def __init__(self) -> None:
        self._actions: dict[str, ProposedAction] = {}

    async def propose(self, action: ProposedAction) -> ProposedAction:
        return self._actions.setdefault(str(action.id), action)  # idempotent by id

    async def get(self, action_id: ActionId) -> ProposedAction | None:
        return self._actions.get(str(action_id))

    async def list(
        self, workspace_id: WorkspaceId, *, status: ActionStatus | None = None
    ) -> Sequence[ProposedAction]:
        actions = [
            a
            for a in self._actions.values()
            if a.workspace_id == workspace_id and (status is None or a.status is status)
        ]
        actions.sort(key=lambda a: a.created_at, reverse=True)
        return actions

    async def update(self, action: ProposedAction) -> ProposedAction:
        self._actions[str(action.id)] = action
        return action


class WikiInbox:
    """In-memory wiki patch reviews (dev backend; durable sibling is PostgresWikiReviewInbox)."""

    def __init__(self) -> None:
        self._reviews: dict[str, WikiPatchReview] = {}

    async def propose(self, review: WikiPatchReview) -> None:
        self._reviews.setdefault(str(review.patch.id), review)

    async def pending(self) -> Sequence[WikiPatchReview]:
        return [r for r in self._reviews.values() if r.status is WikiPatchStatus.PROPOSED]

    async def approve(self, patch_id: str, *, note: str) -> WikiPatchReview | None:
        review = self._reviews.get(patch_id)
        if review is None or review.status is not WikiPatchStatus.PROPOSED:
            return None
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

    async def list(self, workspace_id: WorkspaceId) -> Sequence[Job]:
        return [j for j in self._jobs.values() if j.workspace_id == workspace_id]

    async def get(self, job_id: JobId) -> Job | None:
        return self._jobs.get(str(job_id))

    async def error_for(self, job_id: JobId) -> str | None:
        return self._errors.get(str(job_id))

    async def retry(self, job_id: JobId) -> Job | None:
        job = self._jobs.get(str(job_id))
        if job is None or job.state not in (JobState.FAILED, JobState.RETRYING):
            return None
        self._errors.pop(str(job_id), None)
        revived = job.model_copy(update={"state": JobState.PENDING, "attempts": job.attempts + 1})
        self._jobs[str(job_id)] = revived
        return revived

    def _set_state(self, job_id: str, state: JobState) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
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
        wiki: WikiReviewInbox,
        audit: AuditLog,
        workspace_id: WorkspaceId,
    ) -> None:
        self._approvals = approvals
        self._wiki = wiki
        self._audit = audit
        self._workspace_id = workspace_id

    async def pending(self) -> list[InboxItem]:
        items = [
            InboxItem("action", r.key, f"{r.skill_name}@{r.skill_version}", r.status.value)
            for r in await self._approvals.pending()
        ]
        items += [
            InboxItem("wiki_patch", str(r.patch.id), _patch_summary(r), r.status.value)
            for r in await self._wiki.pending()
        ]
        return items

    async def approve(self, *, kind: str, item_id: str, note: str) -> InboxItem:
        if kind == "action":
            keys = {r.key for r in await self._approvals.pending()}
            if item_id not in keys:
                raise NotFoundError(f"no pending action {item_id!r}")
            await self._approvals.approve(item_id)
            await self._record("SkillAction", item_id, note)
            return InboxItem("action", item_id, item_id, "approved")
        if kind == "wiki_patch":
            review = await self._wiki.approve(item_id, note=note)
            if review is None:
                raise NotFoundError(f"no pending wiki patch {item_id!r}")
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


def _to_request(row: SkillApprovalRow) -> ApprovalRequest:
    return ApprovalRequest(
        key=row.key,
        skill_name=row.skill_name,
        skill_version=row.skill_version,
        status=SkillApprovalStatus(row.status),
    )


class PostgresApprovalQueue:
    """Durable Postgres skill-approval queue, conforming to the runtime ``ApprovalQueue`` protocol.

    It lives here (not metis-core) because it bridges a runtime value (``ApprovalRequest``) to a
    core table; the gateway is the composition root that already imports both. Held approvals
    survive a restart, so a proposed outbound action is not lost.
    """

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], workspace_id: WorkspaceId
    ) -> None:
        self._sessionmaker = sessionmaker
        self._workspace_id = workspace_id

    async def submit(self, skill_input: SkillInput) -> ApprovalRequest:
        key = approval_key(skill_input)
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SkillApprovalRow, (str(self._workspace_id), key))
            if row is not None:
                return _to_request(row)
            session.add(
                SkillApprovalRow(
                    workspace_id=str(self._workspace_id),
                    key=key,
                    skill_name=skill_input.skill_name,
                    skill_version=skill_input.skill_version,
                    status=SkillApprovalStatus.PENDING.value,
                    created_at=datetime.now(UTC),
                )
            )
        return ApprovalRequest(
            key=key, skill_name=skill_input.skill_name, skill_version=skill_input.skill_version
        )

    async def is_approved(self, skill_input: SkillInput) -> bool:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(
                SkillApprovalRow, (str(self._workspace_id), approval_key(skill_input))
            )
        return row is not None and row.status == SkillApprovalStatus.APPROVED.value

    async def approve(self, key: str) -> None:
        await self._set(key, SkillApprovalStatus.APPROVED)

    async def reject(self, key: str) -> None:
        await self._set(key, SkillApprovalStatus.REJECTED)

    async def pending(self) -> Sequence[ApprovalRequest]:
        stmt = (
            select(SkillApprovalRow)
            .where(
                SkillApprovalRow.workspace_id == str(self._workspace_id),
                SkillApprovalRow.status == SkillApprovalStatus.PENDING.value,
            )
            .order_by(SkillApprovalRow.created_at.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [_to_request(row) for row in rows]

    async def _set(self, key: str, status: SkillApprovalStatus) -> None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SkillApprovalRow, (str(self._workspace_id), key))
            if row is not None:
                row.status = status.value


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
        ocr_transcribe: Transcribe | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._sessionmaker = sessionmaker
        self._object_store = object_store
        self._artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
        self._documents = PostgresDocumentStore(sessionmaker)
        self._claims = PostgresClaimStore(sessionmaker)
        self._memory = PostgresMemoryStore(sessionmaker)
        # Index with the same embedder the query engine retrieves with, so vectors are comparable.
        self._indexer = MemoryIndexer(sessionmaker, embedding_router)
        self._builder = MemCellBuilder()  # deterministic, evidence-only (no model call)
        self._query = query_engine
        # The OCR transcriber for low-coverage PDFs (None unless a vision model is wired).
        self._ocr_transcribe = ocr_transcribe

    async def ingest_bytes(
        self, *, filename: str, data: bytes, sensitivity: Sensitivity, connector: str = "upload"
    ) -> IngestOutcome:
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
            connector=connector,
        )
        await self._artifacts.put_blob(data)
        await self._artifacts.put(raw)
        doc, product = await build_normalized_doc_rich(
            raw, data, policy=policy, transcribe=self._ocr_transcribe
        )
        await self._documents.put_normalized(doc)
        parsed, segments = parse_document(
            doc, fmt.segmentation, pages=product.pages, page_count=product.page_count
        )
        await self._documents.put_parsed(parsed)
        await self._documents.put_segments(segments)
        result = BaselineExtractor().extract(doc, parsed.id, segments)
        await self._documents.put_source_spans(str(self._workspace_id), result.source_spans)
        await self._claims.write(result.batch)
        quality = assess(product, segments=len(segments))
        if result.batch.claims:  # consolidate -> index so retrieval can find it
            cell = await self._builder.build(
                workspace_id=self._workspace_id, claims=result.batch.claims
            )
            await self._memory.write_mem_cell(cell)
            await self._indexer.index_mem_cell(cell)
        return IngestOutcome(
            doc_id=str(doc.id),
            media_type=media.media_type,
            segments=len(segments),
            claims=len(result.batch.claims),
            coverage=quality.coverage,
            page_count=quality.page_count,
            tables=quality.tables,
            warnings=quality.warnings,
            parse_path=product.parse_path,
        )

    async def ingest(
        self, *, filename: str, content: str, sensitivity: Sensitivity
    ) -> tuple[str, int]:
        outcome = await self.ingest_bytes(
            filename=filename,
            data=content.encode("utf-8"),
            sensitivity=sensitivity,
            connector="gateway",
        )
        return outcome.doc_id, outcome.claims

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

    async def erase_artifact(self, artifact_id: str) -> ErasureResult | None:
        """Right-to-erasure for one raw artifact: tombstone its derived graph and delete its blob.

        The artifact is resolved *within this workspace* first — the store's ``get`` keys off id
        alone, so this workspace filter is the isolation guard that turns a cross-workspace id into
        a 404 rather than a cross-tenant delete."""
        async with unit_of_work(self._sessionmaker) as session:
            owned = await session.scalar(
                select(RawArtifactRow.id).where(
                    RawArtifactRow.id == artifact_id,
                    RawArtifactRow.workspace_id == str(self._workspace_id),
                )
            )
        if owned is None:
            return None
        return await erase_artifact_core(
            self._sessionmaker,
            self._object_store,
            workspace_id=str(self._workspace_id),
            artifact_id=artifact_id,
        )

    async def erase_source(self, source_id: str) -> ErasureSummary:
        """Erase every artifact this source produced in this workspace (cascade + blob each)."""
        return await erase_source_core(
            self._sessionmaker,
            self._object_store,
            workspace_id=str(self._workspace_id),
            source_id=source_id,
        )

    async def erase_workspace_artifacts(self) -> ErasureSummary:
        """Erase every artifact in this workspace (whole evidence graph, cascade + blob each)."""
        return await erase_workspace_artifacts_core(
            self._sessionmaker, self._object_store, workspace_id=str(self._workspace_id)
        )

    async def claim_evidence(self, claim_id: str) -> ClaimEvidence | None:
        claim = await self._claims.get(ClaimId(claim_id))
        if claim is None or str(claim.provenance.workspace_id) != str(self._workspace_id):
            return None
        spans = tuple([await self._span_evidence(ref) for ref in claim.source_spans])
        return ClaimEvidence(
            claim_id=claim_id,
            text=claim.text,
            confidence=claim.confidence,
            negated=claim.negated,
            sensitivity=claim.policy.sensitivity.value,
            spans=spans,
        )

    async def _span_evidence(self, ref: SourceSpanRef) -> SpanEvidence:
        span = await self._documents.get_source_span(ref.source_span_id)
        quote: str | None = None
        doc_id = (
            ref.doc_id if ref.doc_id is not None else (span.doc_id if span is not None else None)
        )
        if span is not None and span.doc_id is not None:
            doc = await self._documents.get_normalized(span.doc_id)
            if doc is not None:
                quote = doc.text[span.char_start : span.char_end]
        return SpanEvidence(
            source_span_id=str(ref.source_span_id),
            artifact_id=str(ref.artifact_id),
            doc_id=str(doc_id) if doc_id is not None else None,
            char_start=span.char_start if span is not None else 0,
            char_end=span.char_end if span is not None else 0,
            page=span.page if span is not None else None,
            quote=quote,
        )

    async def artifact_evidence(self, artifact_id: str) -> ArtifactEvidence | None:
        raw = await self._artifacts.get(ArtifactRef(artifact_id=ArtifactId(artifact_id)))
        if raw is None or str(raw.provenance.workspace_id) != str(self._workspace_id):
            return None
        return _artifact_evidence(raw)

    async def mem_cell_evidence(self, mem_cell_id: str) -> MemCellEvidence | None:
        cell = await self._memory.get_mem_cell(MemCellId(mem_cell_id))
        if cell is None or str(cell.provenance.workspace_id) != str(self._workspace_id):
            return None
        return MemCellEvidence(
            mem_cell_id=mem_cell_id,
            summary=cell.summary,
            sensitivity=cell.policy.sensitivity.value,
            claim_ids=tuple(str(c.claim_id) for c in cell.claims),
        )

    async def list_contradictions(
        self, *, status: ContradictionStatus | None
    ) -> Sequence[Contradiction]:
        found = await self._memory.query_contradictions(
            MemoryScope(workspace_id=self._workspace_id)
        )
        return [c for c in found if status is None or c.status is status]

    async def resolve_contradiction(
        self, contradiction_id: str, *, status: ContradictionStatus
    ) -> Contradiction | None:
        return await self._memory.set_contradiction_status(
            ContradictionId(contradiction_id), status, workspace_id=self._workspace_id
        )

    async def list_memory(self) -> Sequence[MemCell]:
        return await self._memory.query_cells(MemoryScope(workspace_id=self._workspace_id))

    async def revise_mem_cell(
        self, mem_cell_id: str, *, op: MemoryOp, reason: str, actor: str
    ) -> MemCell | None:
        cell = await self._memory.get_mem_cell(MemCellId(mem_cell_id))
        if cell is None or str(cell.provenance.workspace_id) != str(self._workspace_id):
            return None
        await self._memory.apply_patch(
            MemoryPatch(
                id=new_id(MemoryPatchId),
                provenance=Provenance(
                    workspace_id=self._workspace_id,
                    attribution=Attribution(agent_kind=AgentKind.HUMAN, agent=actor),
                ),
                policy=cell.policy,
                created_at=datetime.now(UTC),
                op=op,
                target_id=mem_cell_id,
                reason=reason,
            )
        )
        return cell


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


@dataclass(frozen=True)
class GoogleOAuthConfig:
    """Google OAuth client config + the consent-URL builder for the gateway's connect flow."""

    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    redirect_uri: str
    scopes: str

    def authorize_url(self, *, state: str) -> str:
        """The Google consent URL; ``access_type=offline`` + ``prompt=consent`` ask for a refresh
        token, and ``state`` is the CSRF token the callback verifies."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scopes,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"


def _build_credentials(settings: GatewaySettings) -> EncryptedCredentialStore | None:
    """The encrypted credential store the OAuth callback writes refresh tokens into."""
    if not settings.cred_store_key:
        return None
    return EncryptedCredentialStore(Cryptobox(settings.cred_store_key))


def _build_google_oauth(settings: GatewaySettings) -> GoogleOAuthConfig | None:
    """The Google consent config (None when no client id is set, i.e. the flow is disabled)."""
    if not settings.google_client_id:
        return None
    return GoogleOAuthConfig(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        auth_url=settings.google_auth_url,
        token_url=settings.google_token_url,
        redirect_uri=settings.google_redirect_uri,
        scopes=settings.google_scopes,
    )


@dataclass
class Backend:
    """Everything the routers depend on, wired once at app assembly (memory or Postgres)."""

    workspace_id: WorkspaceId
    workspace: Workspace
    agent: AgentLoop
    skills: SkillRegistry
    skill_runner: SkillRunner
    jobs: JobOps
    audit: AuditLog
    sources: SourceStore
    wiki: WikiReviewInbox
    inbox: ApprovalInbox
    actions: ActionStore = field(default_factory=InMemoryActionStore)
    model_caller: ModelCaller | None = None  # the caller the command interpreter uses (None = none)
    identity: IdentityStore = field(default_factory=InMemoryIdentityStore)
    connectors: ConnectorRegistry = field(default_factory=ConnectorRegistry.with_defaults)
    object_store: ObjectStore = field(default_factory=InMemoryObjectStore)
    engine: AsyncEngine | None = None  # set for the Postgres backend; disposed at shutdown
    http_client: httpx.AsyncClient | None = (
        None  # the local model client (chat + embeddings); closed at shutdown
    )
    model_closers: tuple[Callable[[], Awaitable[None]], ...] = ()  # cloud clients to close
    spend: SpendTracker | None = None  # per-workspace model spend (None when no model is wired)
    model_manifests: tuple[ModelCapability, ...] = ()  # registered capability manifests (operators)
    credentials: EncryptedCredentialStore | None = None  # encrypted connector secrets at rest
    google_oauth: GoogleOAuthConfig | None = None  # the Google consent config (None = disabled)
    oauth_states: dict[str, str] = field(default_factory=dict)  # pending CSRF state -> connector
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
        sources=InMemorySourceStore(),
        actions=InMemoryActionStore(),
        model_caller=plane.make_caller(allow_external=True),
        wiki=wiki,
        inbox=inbox,
        object_store=object_store,
        http_client=plane.local_client,
        model_closers=plane.closers,
        spend=plane.spend,
        model_manifests=plane.manifests,
        credentials=_build_credentials(settings),
        google_oauth=_build_google_oauth(settings),
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
    # the plane. Embeddings: an embed-kind manifest (self-hosted TEI) when registered, else local
    # bge-m3 when an endpoint is set, else stub vectors. The answer generator degrades to extractive
    # on a model error.
    plane = build_model_plane(settings, audit_sink=audit)
    embedding_router: EmbeddingRouter = build_embedding_router(
        manifests=plane.manifests,
        manifest_client=plane.manifest_client,
        local_client=plane.local_client,
        local_endpoint=settings.model_endpoint,
        local_model=settings.embedding_model,
    )

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
        # OCR for low-coverage PDFs goes through the same model caller (so the workspace's external
        # policy + the router's vision routing apply); None when no model is wired.
        transcribe = model_transcriber(caller, ws_id) if caller is not None else None
        return PostgresWorkspace(
            workspace_id=ws_id,
            sessionmaker=sessionmaker,
            object_store=object_store,
            query_engine=query_engine,
            embedding_router=embedding_router,
            ocr_transcribe=transcribe,
        )

    workspace = _workspace_factory(workspace_id, allow_external=True)
    skills = (
        SkillRegistry.discover(Path(settings.skills_root))
        if settings.skills_root
        else SkillRegistry()
    )
    skill_runner = SkillRunner(
        skills,
        audit_sink=audit,
        object_store=object_store,
        workspace_id=workspace_id,
        approvals=PostgresApprovalQueue(sessionmaker, workspace_id),
    )
    agent = AgentLoop(
        answerer=workspace, skill_runner=skill_runner, registry=skills, audit_sink=audit
    )
    wiki = PostgresWikiReviewInbox(sessionmaker, workspace_id)
    inbox = ApprovalInbox(skill_runner.approvals, wiki, audit, workspace_id)

    return Backend(
        workspace_id=workspace_id,
        workspace=workspace,
        agent=agent,
        skills=skills,
        skill_runner=skill_runner,
        jobs=PostgresJobQueue(sessionmaker),  # durable: jobs survive restart; workers lease over it
        audit=audit,
        sources=PostgresSourceStore(sessionmaker),  # durable: source configs/cursors/runs persist
        actions=PostgresActionStore(sessionmaker),  # durable: proposed actions + decisions persist
        model_caller=plane.make_caller(allow_external=True),
        wiki=wiki,
        inbox=inbox,
        identity=PostgresIdentityStore(sessionmaker),
        object_store=object_store,
        engine=engine,
        http_client=plane.local_client,
        model_closers=plane.closers,
        spend=plane.spend,
        model_manifests=plane.manifests,
        credentials=_build_credentials(settings),
        google_oauth=_build_google_oauth(settings),
        workspace_factory=_workspace_factory,
    )
