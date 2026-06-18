"""Interpreted memory: MemCell, MemScene, Profile, Foresight, Contradiction, and
the append-only MemoryPatch.
"""

from __future__ import annotations

from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from metis_protocol.artifacts import Artifact
from metis_protocol.base import ProtocolModel
from metis_protocol.enums import (
    ContradictionStatus,
    ForesightStatus,
    MemoryOp,
    ProfileScope,
)
from metis_protocol.ids import (
    ContradictionId,
    ForesightId,
    MemCellId,
    MemoryPatchId,
    MemSceneId,
    ProfileId,
)
from metis_protocol.refs import ClaimRef, EntityRef, MemCellRef, MemSceneRef, SourceSpanRef
from metis_protocol.versioning import schema


@schema
class MemCell(Artifact[MemCellId]):
    """An episode-like interpreted memory, backed by claims and source spans."""

    summary: str
    content: str
    claims: tuple[ClaimRef, ...] = ()
    source_spans: tuple[SourceSpanRef, ...] = Field(min_length=1)
    scene: MemSceneRef | None = None
    occurred_at: AwareDatetime | None = None
    salience: float | None = Field(default=None, ge=0.0, le=1.0)
    supersedes: MemCellRef | None = None


@schema
class MemScene(Artifact[MemSceneId]):
    """A thematic cluster of related MemCells and claims."""

    title: str
    summary: str
    mem_cells: tuple[MemCellRef, ...] = ()
    claims: tuple[ClaimRef, ...] = ()
    topic: str | None = None
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None


class ProfileFact(ProtocolModel):
    """One stable fact in a profile, with its supporting claims and conflict flag."""

    key: str
    value: str
    claims: tuple[ClaimRef, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    conflicting: bool = False


@schema
class Profile(Artifact[ProfileId]):
    """Stable workspace/user/company/person facts with conflict tracking."""

    scope: ProfileScope
    label: str
    subject: EntityRef | None = None
    facts: tuple[ProfileFact, ...] = ()


@schema
class Foresight(Artifact[ForesightId]):
    """An expected future state with a validity window and supporting evidence."""

    statement: str
    predicted_state: str
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    status: ForesightStatus = ForesightStatus.ACTIVE
    claims: tuple[ClaimRef, ...] = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to must be >= valid_from")
        return self


@schema
class Contradiction(Artifact[ContradictionId]):
    """A detected conflict between two or more claims — surfaced, never silently merged."""

    summary: str
    explanation: str
    status: ContradictionStatus = ContradictionStatus.OPEN
    claims: tuple[ClaimRef, ...] = Field(min_length=2)


@schema
class MemoryPatch(Artifact[MemoryPatchId]):
    """An append-only memory revision: create, supersede, or retract a memory object."""

    op: MemoryOp
    target_id: str  # id of the affected memory object
    supersedes_id: str | None = None
    reason: str = ""
