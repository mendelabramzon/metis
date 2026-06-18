"""Machine-truth tables: claims, entities, events, and extraction batches.

Claims cite source spans via refs inside ``body`` (denormalized with artifact ids),
not via FKs, so the Stage 1 contract suites pass with synthetic ids. The batch's
``parsed_doc_id`` is a plain column for the same reason.
"""

from __future__ import annotations

from sqlalchemy import Float, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import ArtifactRow, BodyMixin, IdMixin, VersionMixin, WorkspaceMixin
from metis_core.db.types import TZDateTime


class ClaimRow(Base, ArtifactRow):
    __tablename__ = "claims"
    __table_args__ = (
        Index(
            "ix_claims_fts",
            text("to_tsvector('english', body ->> 'text')"),
            postgresql_using="gin",
        ),
    )

    predicate: Mapped[str | None] = mapped_column(nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float)


class EntityRow(Base, ArtifactRow):
    __tablename__ = "entities"

    kind: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(index=True)


class EventRow(Base, ArtifactRow):
    __tablename__ = "events"

    occurred_at: Mapped[TZDateTime | None] = mapped_column(nullable=True)


class ExtractionBatchRow(Base, IdMixin, WorkspaceMixin, VersionMixin, BodyMixin):
    __tablename__ = "extraction_batches"

    parsed_doc_id: Mapped[str] = mapped_column(index=True)
