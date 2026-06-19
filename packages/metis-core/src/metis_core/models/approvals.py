"""The skill-approval queue table: one row per (workspace, approval key).

The durable backing for held outbound/destructive skill runs, so a pending approval survives a
restart. The key is a stable hash of skill + arguments (the runtime owns it); the row is plain
columns (no body) since an ``ApprovalRequest`` is four scalar fields.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.types import Id, TZDateTime


class SkillApprovalRow(Base):
    __tablename__ = "skill_approvals"

    workspace_id: Mapped[Id] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill_name: Mapped[str] = mapped_column()
    skill_version: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[TZDateTime] = mapped_column(index=True)
