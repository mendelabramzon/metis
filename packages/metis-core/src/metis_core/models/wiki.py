"""Wiki tables: pages (compiled projection) and the patches that write them.

Pages are unique by ``(workspace_id, slug)``. Patches' ``page_id`` is a plain column
(a create patch has no page yet).
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import ArtifactRow


class WikiPageRow(Base, ArtifactRow):
    __tablename__ = "wiki_pages"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)

    slug: Mapped[str] = mapped_column(index=True)


class WikiPatchRow(Base, ArtifactRow):
    __tablename__ = "wiki_patches"

    op: Mapped[str] = mapped_column(index=True)
    page_id: Mapped[str | None] = mapped_column(nullable=True, index=True)
