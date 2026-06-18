"""Interpreted-memory tables: mem cells, scenes, profiles, foresights, contradictions,
and the append-only memory patches.

Memory is append-only: supersede/retract flip flags on the target row (it stays
queryable and auditable) rather than deleting it. Cross-references (scene, supersedes,
target) are plain columns, not FKs, so superseded rows and forward refs stay valid.
"""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import ArtifactRow
from metis_core.db.types import Embedding, TZDateTime


class MemCellRow(Base, ArtifactRow):
    __tablename__ = "mem_cells"

    scene_id: Mapped[str | None] = mapped_column(nullable=True, index=True)
    supersedes_id: Mapped[str | None] = mapped_column(nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    retracted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    occurred_at: Mapped[TZDateTime | None] = mapped_column(nullable=True)
    embedding: Mapped[Embedding] = mapped_column()


class MemSceneRow(Base, ArtifactRow):
    __tablename__ = "mem_scenes"

    topic: Mapped[str | None] = mapped_column(nullable=True)


class ProfileRow(Base, ArtifactRow):
    __tablename__ = "profiles"

    scope: Mapped[str] = mapped_column(index=True)
    label: Mapped[str] = mapped_column()


class ForesightRow(Base, ArtifactRow):
    __tablename__ = "foresights"

    status: Mapped[str] = mapped_column(index=True)
    valid_from: Mapped[TZDateTime] = mapped_column()
    valid_to: Mapped[TZDateTime] = mapped_column()


class ContradictionRow(Base, ArtifactRow):
    __tablename__ = "contradictions"

    status: Mapped[str] = mapped_column(index=True)


class MemoryPatchRow(Base, ArtifactRow):
    __tablename__ = "memory_patches"

    op: Mapped[str] = mapped_column(index=True)
    target_id: Mapped[str] = mapped_column(index=True)
    supersedes_id: Mapped[str | None] = mapped_column(nullable=True)
