"""The job-queue table, leased with ``FOR UPDATE SKIP LOCKED`` (see jobs/queue.py)."""

from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import BodyMixin, IdMixin, VersionMixin, WorkspaceMixin
from metis_core.db.types import TZDateTime


class JobRow(Base, IdMixin, WorkspaceMixin, VersionMixin, BodyMixin):
    __tablename__ = "jobs"

    kind: Mapped[str] = mapped_column(index=True)
    state: Mapped[str] = mapped_column(index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[TZDateTime] = mapped_column(index=True)
    scheduled_at: Mapped[TZDateTime | None] = mapped_column(nullable=True)
    locked_at: Mapped[TZDateTime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(nullable=True)
