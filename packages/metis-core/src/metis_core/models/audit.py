"""The append-only, hash-chained audit table.

``seq`` is a per-workspace monotonic counter; ``audit_hash`` chains each row to the
previous one's hash, so tampering breaks the chain (verified by ``audit/verify.py``).
"""

from __future__ import annotations

from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import BodyMixin, IdMixin, VersionMixin, WorkspaceMixin
from metis_core.db.types import TZDateTime


class AuditEventRow(Base, IdMixin, WorkspaceMixin, VersionMixin, BodyMixin):
    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("workspace_id", "seq"),)

    seq: Mapped[int] = mapped_column(BigInteger, index=True)
    occurred_at: Mapped[TZDateTime] = mapped_column(index=True)
    prev_hash: Mapped[str | None] = mapped_column(nullable=True)
    audit_hash: Mapped[str] = mapped_column()
