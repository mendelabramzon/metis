"""Evidence-truth tables: raw artifacts, normalized/parsed docs, segments, source spans.

Foreign keys encode the evidence chain (artifact <- doc <- parsed <- segment, and
span -> artifact); write order is controlled by callers. ``raw_artifacts`` is
deduplicated by ``(workspace_id, content_hash)``.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import (
    ArtifactRow,
    BodyMixin,
    EmbeddedArtifactRow,
    IdMixin,
    VersionMixin,
    WorkspaceMixin,
)


class RawArtifactRow(Base, ArtifactRow):
    __tablename__ = "raw_artifacts"
    __table_args__ = (UniqueConstraint("workspace_id", "content_hash"),)

    kind: Mapped[str] = mapped_column()
    content_hash: Mapped[str] = mapped_column(index=True)
    media_type: Mapped[str] = mapped_column()
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_ref: Mapped[str] = mapped_column()


class NormalizedDocRow(Base, ArtifactRow):
    __tablename__ = "normalized_docs"

    artifact_id: Mapped[str] = mapped_column(ForeignKey("raw_artifacts.id"), index=True)
    media_type: Mapped[str] = mapped_column()


class ParsedDocRow(Base, ArtifactRow):
    __tablename__ = "parsed_docs"

    doc_id: Mapped[str] = mapped_column(ForeignKey("normalized_docs.id"), index=True)


class SegmentRow(Base, EmbeddedArtifactRow):
    __tablename__ = "segments"
    __table_args__ = (
        Index(
            "ix_segments_fts",
            text("to_tsvector('english', body ->> 'text')"),
            postgresql_using="gin",
        ),
    )

    parsed_doc_id: Mapped[str] = mapped_column(ForeignKey("parsed_docs.id"), index=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("normalized_docs.id"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    # Chunk embedding for naive-RAG retrieval (dim fixed in Stage 5, ADR 0014) inherited
    # from EmbeddedArtifactRow.


class SourceSpanRow(Base, IdMixin, WorkspaceMixin, VersionMixin, BodyMixin):
    """A source span (VersionedModel, not an Artifact): no provenance/policy envelope."""

    __tablename__ = "source_spans"

    artifact_id: Mapped[str] = mapped_column(ForeignKey("raw_artifacts.id"), index=True)
    doc_id: Mapped[str | None] = mapped_column(nullable=True)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
