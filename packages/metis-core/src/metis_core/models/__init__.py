"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from __future__ import annotations

from metis_core.models.approvals import SkillApprovalRow
from metis_core.models.artifacts import (
    NormalizedDocRow,
    ParsedDocRow,
    RawArtifactRow,
    SegmentRow,
    SourceSpanRow,
)
from metis_core.models.audit import AuditEventRow
from metis_core.models.claims import ClaimRow, EntityRow, EventRow, ExtractionBatchRow
from metis_core.models.identity import (
    OrganizationRow,
    UserRow,
    WorkspaceMembershipRow,
    WorkspaceModelPolicyRow,
    WorkspaceRow,
)
from metis_core.models.jobs import JobRow
from metis_core.models.memory import (
    ContradictionRow,
    ForesightRow,
    MemCellRow,
    MemoryPatchRow,
    MemSceneRow,
    ProfileRow,
)
from metis_core.models.sources import ConnectorRunRow, SourceConfigRow, SourceCursorRow
from metis_core.models.wiki import WikiPageRow, WikiPatchReviewRow, WikiPatchRow

__all__ = [
    "AuditEventRow",
    "ClaimRow",
    "ConnectorRunRow",
    "ContradictionRow",
    "EntityRow",
    "EventRow",
    "ExtractionBatchRow",
    "ForesightRow",
    "JobRow",
    "MemCellRow",
    "MemSceneRow",
    "MemoryPatchRow",
    "NormalizedDocRow",
    "OrganizationRow",
    "ParsedDocRow",
    "ProfileRow",
    "RawArtifactRow",
    "SegmentRow",
    "SkillApprovalRow",
    "SourceConfigRow",
    "SourceCursorRow",
    "SourceSpanRow",
    "UserRow",
    "WikiPageRow",
    "WikiPatchReviewRow",
    "WikiPatchRow",
    "WorkspaceMembershipRow",
    "WorkspaceModelPolicyRow",
    "WorkspaceRow",
]
