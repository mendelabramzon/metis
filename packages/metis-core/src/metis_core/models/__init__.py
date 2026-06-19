"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from __future__ import annotations

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
from metis_core.models.wiki import WikiPageRow, WikiPatchRow

__all__ = [
    "AuditEventRow",
    "ClaimRow",
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
    "SourceSpanRow",
    "UserRow",
    "WikiPageRow",
    "WikiPatchRow",
    "WorkspaceMembershipRow",
    "WorkspaceRow",
]
