"""Durable store interfaces implemented by ``metis-core``. All are async (ADR 0008).

These are the contracts the abstract suites in ``metis_protocol.contract_tests``
exercise, so an implementation can prove conformance before it is trusted.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from metis_protocol.artifacts import NormalizedDoc, ParsedDoc, RawArtifact, Segment
from metis_protocol.claims import Claim, ClaimWriteResult, ExtractionBatch
from metis_protocol.enums import Role
from metis_protocol.identity import (
    Organization,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceModelPolicy,
)
from metis_protocol.ids import (
    ClaimId,
    ContradictionId,
    DocId,
    ForesightId,
    MemCellId,
    MemSceneId,
    ParsedDocId,
    ProfileId,
    SegmentId,
    SourceId,
    UserId,
    WikiPageId,
    WorkspaceId,
)
from metis_protocol.memory import (
    Contradiction,
    Foresight,
    MemCell,
    MemoryPatch,
    MemScene,
    Profile,
)
from metis_protocol.query import ClaimFilter, MemoryScope
from metis_protocol.refs import ArtifactRef
from metis_protocol.sources import ConnectorRun, SourceConfig, SourceCursor
from metis_protocol.wiki import WikiPage, WikiPatch


@runtime_checkable
class ArtifactStore(Protocol):
    async def put(self, raw: RawArtifact) -> ArtifactRef: ...

    async def get(self, ref: ArtifactRef) -> RawArtifact | None: ...


@runtime_checkable
class DocumentStore(Protocol):
    async def put_normalized(self, doc: NormalizedDoc) -> DocId: ...

    async def get_normalized(self, doc_id: DocId) -> NormalizedDoc | None: ...

    async def put_parsed(self, doc: ParsedDoc) -> ParsedDocId: ...

    async def get_parsed(self, parsed_doc_id: ParsedDocId) -> ParsedDoc | None: ...

    async def put_segments(self, segments: Sequence[Segment]) -> Sequence[SegmentId]: ...

    async def get_segment(self, segment_id: SegmentId) -> Segment | None: ...


@runtime_checkable
class ClaimStore(Protocol):
    async def write(self, batch: ExtractionBatch) -> ClaimWriteResult: ...

    async def query(self, claim_filter: ClaimFilter) -> Sequence[Claim]: ...

    async def get(self, claim_id: ClaimId) -> Claim | None: ...


@runtime_checkable
class MemoryStore(Protocol):
    async def write_mem_cell(self, cell: MemCell) -> MemCellId: ...

    async def get_mem_cell(self, mem_cell_id: MemCellId) -> MemCell | None: ...

    async def write_scene(self, scene: MemScene) -> MemSceneId: ...

    async def get_scene(self, mem_scene_id: MemSceneId) -> MemScene | None: ...

    async def apply_patch(self, patch: MemoryPatch) -> None: ...

    async def query_cells(self, scope: MemoryScope) -> Sequence[MemCell]: ...

    # Maintainer outputs (Stage 6). Scenes/profiles/foresights are recomputable
    # projections (upserted on rebuild); contradictions are append-only findings.
    async def write_profile(self, profile: Profile) -> ProfileId: ...

    async def get_profile(self, profile_id: ProfileId) -> Profile | None: ...

    async def write_contradiction(self, contradiction: Contradiction) -> ContradictionId: ...

    async def query_contradictions(self, scope: MemoryScope) -> Sequence[Contradiction]: ...

    async def write_foresight(self, foresight: Foresight) -> ForesightId: ...

    async def query_foresights(self, scope: MemoryScope) -> Sequence[Foresight]: ...


@runtime_checkable
class WikiStore(Protocol):
    async def get_page(self, wiki_page_id: WikiPageId) -> WikiPage | None: ...

    async def get_page_by_slug(self, slug: str) -> WikiPage | None: ...

    async def apply_patch(self, patch: WikiPatch) -> WikiPageId: ...


@runtime_checkable
class IdentityStore(Protocol):
    """Organizations, users, workspaces, and memberships — the control plane the gateway
    resolves a caller and their workspace access from. ``resolve_role`` is the isolation gate.
    """

    async def create_organization(self, org: Organization) -> Organization: ...

    async def create_user(self, user: User) -> User: ...

    async def create_workspace(self, workspace: Workspace) -> Workspace: ...

    async def add_membership(self, membership: WorkspaceMembership) -> WorkspaceMembership: ...

    async def get_user(self, user_id: UserId) -> User | None: ...

    async def get_user_by_email(self, email: str) -> User | None: ...

    async def get_workspace(self, workspace_id: WorkspaceId) -> Workspace | None: ...

    async def resolve_role(self, *, user_id: UserId, workspace_id: WorkspaceId) -> Role | None: ...

    async def workspaces_for_user(self, user_id: UserId) -> Sequence[Workspace]: ...

    async def members_of(self, workspace_id: WorkspaceId) -> Sequence[WorkspaceMembership]: ...

    async def get_model_policy(self, workspace_id: WorkspaceId) -> WorkspaceModelPolicy: ...

    async def set_model_policy(self, policy: WorkspaceModelPolicy) -> WorkspaceModelPolicy: ...

    async def deactivate_user(self, user_id: UserId) -> User | None: ...

    # Soft-disable a user (active=False) so the auth boundary rejects them; their audit trail stays.
    # Returns the updated user, or None if unknown.


@runtime_checkable
class SourceStore(Protocol):
    """Connector-backed source configs, their resume cursors, and connector-run history — the
    durable substrate the ingest worker polls and the operator source dashboard reads. Writes are
    idempotent by id; cursors and runs upsert (a cursor advances, a run opens then closes).
    """

    async def register(self, config: SourceConfig) -> SourceConfig: ...

    async def get(self, source_id: SourceId) -> SourceConfig | None: ...

    async def list(self, workspace_id: WorkspaceId) -> Sequence[SourceConfig]: ...

    async def list_all(self) -> Sequence[SourceConfig]: ...

    async def get_cursor(self, source_id: SourceId) -> SourceCursor | None: ...

    async def set_cursor(self, cursor: SourceCursor) -> SourceCursor: ...

    async def record_run(self, run: ConnectorRun) -> ConnectorRun: ...

    async def runs_for(self, source_id: SourceId, *, limit: int = 50) -> Sequence[ConnectorRun]: ...

    async def delete(self, source_id: SourceId) -> None: ...

    # Remove the source registration (config + cursor + run history). The artifacts it produced are
    # erased separately (right-to-erasure), not here.
