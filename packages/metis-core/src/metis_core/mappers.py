"""Translation between protocol models (wire/contract truth) and ORM rows (storage).

Each ``*_to_row`` extracts the indexed/FK columns and stores the full protocol model
dump in ``body``; ``to_model`` reconstructs by validating ``body`` (translate-on-read,
ADR 0010). The protocol models remain authoritative; rows are storage detail.
"""

from __future__ import annotations

from typing import Any

from metis_core.db.mixins import BodyMixin
from metis_core.models import (
    ClaimRow,
    ContradictionRow,
    EntityRow,
    EventRow,
    ExtractionBatchRow,
    ForesightRow,
    JobRow,
    MemCellRow,
    MemoryPatchRow,
    MemSceneRow,
    NormalizedDocRow,
    OrganizationRow,
    ParsedDocRow,
    ProfileRow,
    RawArtifactRow,
    SegmentRow,
    SourceSpanRow,
    UserRow,
    WikiPageRow,
    WikiPatchRow,
    WorkspaceMembershipRow,
    WorkspaceModelPolicyRow,
    WorkspaceRow,
)
from metis_protocol import (
    Artifact as ProtocolArtifact,
)
from metis_protocol import (
    Claim,
    Contradiction,
    Entity,
    Event,
    ExtractionBatch,
    Foresight,
    Job,
    MemCell,
    MemoryPatch,
    MemScene,
    NormalizedDoc,
    Organization,
    ParsedDoc,
    Profile,
    RawArtifact,
    Segment,
    SourceSpan,
    User,
    VersionedModel,
    WikiPage,
    WikiPatch,
    Workspace,
    WorkspaceMembership,
    WorkspaceModelPolicy,
)


def to_model[M: VersionedModel](row: BodyMixin, model_type: type[M]) -> M:
    """Reconstruct a protocol model from a row's ``body``."""
    return model_type.model_validate(row.body)


def _artifact_cols(model: ProtocolArtifact[Any]) -> dict[str, Any]:
    """The columns common to every artifact table, plus the full body dump."""
    return {
        "id": str(model.id),
        "workspace_id": str(model.provenance.workspace_id),
        "schema_version": model.schema_version,
        "sensitivity": model.policy.sensitivity.value,
        "created_at": model.created_at,
        "tombstoned_at": model.tombstoned_at,
        "body": model.model_dump(mode="json"),
    }


def raw_artifact_to_row(m: RawArtifact) -> RawArtifactRow:
    return RawArtifactRow(
        **_artifact_cols(m),
        kind=m.kind.value,
        content_hash=m.content_hash,
        media_type=m.media_type,
        byte_size=m.byte_size,
        storage_ref=m.storage_ref,
    )


def normalized_doc_to_row(m: NormalizedDoc) -> NormalizedDocRow:
    return NormalizedDocRow(
        **_artifact_cols(m), artifact_id=str(m.artifact_id), media_type=m.media_type
    )


def parsed_doc_to_row(m: ParsedDoc) -> ParsedDocRow:
    return ParsedDocRow(**_artifact_cols(m), doc_id=str(m.doc_id))


def segment_to_row(m: Segment) -> SegmentRow:
    return SegmentRow(
        **_artifact_cols(m),
        parsed_doc_id=str(m.parsed_doc_id),
        doc_id=str(m.doc_id),
        order=m.order,
        embedding=None,
    )


def source_span_to_row(m: SourceSpan, *, workspace_id: str) -> SourceSpanRow:
    return SourceSpanRow(
        id=str(m.id),
        workspace_id=workspace_id,
        schema_version=m.schema_version,
        artifact_id=str(m.artifact_id),
        doc_id=str(m.doc_id) if m.doc_id is not None else None,
        char_start=m.char_start,
        char_end=m.char_end,
        body=m.model_dump(mode="json"),
    )


def claim_to_row(m: Claim) -> ClaimRow:
    return ClaimRow(**_artifact_cols(m), predicate=m.predicate, confidence=m.confidence)


def entity_to_row(m: Entity) -> EntityRow:
    return EntityRow(**_artifact_cols(m), kind=m.kind.value, name=m.name)


def event_to_row(m: Event) -> EventRow:
    return EventRow(**_artifact_cols(m), occurred_at=m.occurred_at)


def extraction_batch_to_row(m: ExtractionBatch) -> ExtractionBatchRow:
    return ExtractionBatchRow(
        id=str(m.id),
        workspace_id=str(m.workspace_id),
        schema_version=m.schema_version,
        parsed_doc_id=str(m.parsed_doc_id),
        body=m.model_dump(mode="json"),
    )


def mem_cell_to_row(m: MemCell) -> MemCellRow:
    return MemCellRow(
        **_artifact_cols(m),
        scene_id=str(m.scene.mem_scene_id) if m.scene is not None else None,
        supersedes_id=str(m.supersedes.mem_cell_id) if m.supersedes is not None else None,
        occurred_at=m.occurred_at,
    )


def mem_scene_to_row(m: MemScene) -> MemSceneRow:
    return MemSceneRow(**_artifact_cols(m), topic=m.topic)


def profile_to_row(m: Profile) -> ProfileRow:
    return ProfileRow(**_artifact_cols(m), scope=m.scope.value, label=m.label)


def foresight_to_row(m: Foresight) -> ForesightRow:
    return ForesightRow(
        **_artifact_cols(m),
        status=m.status.value,
        valid_from=m.valid_from,
        valid_to=m.valid_to,
    )


def contradiction_to_row(m: Contradiction) -> ContradictionRow:
    return ContradictionRow(**_artifact_cols(m), status=m.status.value)


def memory_patch_to_row(m: MemoryPatch) -> MemoryPatchRow:
    return MemoryPatchRow(
        **_artifact_cols(m),
        op=m.op.value,
        target_id=m.target_id,
        supersedes_id=m.supersedes_id,
    )


def wiki_page_to_row(m: WikiPage) -> WikiPageRow:
    return WikiPageRow(**_artifact_cols(m), slug=m.slug)


def wiki_patch_to_row(m: WikiPatch) -> WikiPatchRow:
    return WikiPatchRow(
        **_artifact_cols(m),
        op=m.op.value,
        page_id=str(m.page_id) if m.page_id is not None else None,
    )


def job_to_row(m: Job) -> JobRow:
    return JobRow(
        id=str(m.id),
        workspace_id=str(m.workspace_id),
        schema_version=m.schema_version,
        kind=m.kind,
        state=m.state.value,
        attempts=m.attempts,
        created_at=m.created_at,
        scheduled_at=m.scheduled_at,
        body=m.model_dump(mode="json"),
    )


def organization_to_row(m: Organization) -> OrganizationRow:
    return OrganizationRow(
        id=str(m.id),
        schema_version=m.schema_version,
        name=m.name,
        created_at=m.created_at,
        body=m.model_dump(mode="json"),
    )


def user_to_row(m: User) -> UserRow:
    return UserRow(
        id=str(m.id),
        schema_version=m.schema_version,
        organization_id=str(m.organization_id),
        email=m.email,
        created_at=m.created_at,
        body=m.model_dump(mode="json"),
    )


def workspace_to_row(m: Workspace) -> WorkspaceRow:
    return WorkspaceRow(
        id=str(m.id),
        schema_version=m.schema_version,
        organization_id=str(m.organization_id),
        kind=m.kind.value,
        owner_id=str(m.owner_id) if m.owner_id is not None else None,
        created_at=m.created_at,
        body=m.model_dump(mode="json"),
    )


def membership_to_row(m: WorkspaceMembership) -> WorkspaceMembershipRow:
    return WorkspaceMembershipRow(
        id=str(m.id),
        schema_version=m.schema_version,
        workspace_id=str(m.workspace_id),
        user_id=str(m.user_id),
        role=m.role.value,
        created_at=m.created_at,
        body=m.model_dump(mode="json"),
    )


def model_policy_to_row(m: WorkspaceModelPolicy) -> WorkspaceModelPolicyRow:
    return WorkspaceModelPolicyRow(
        workspace_id=str(m.workspace_id),
        schema_version=m.schema_version,
        allow_external_models=m.allow_external_models,
        daily_cost_cap_usd=m.daily_cost_cap_usd,
        body=m.model_dump(mode="json"),
    )
