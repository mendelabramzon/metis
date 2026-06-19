"""Identity/tenancy tables: organizations, users, workspaces, memberships.

Control-plane entities, so unlike the artifact tables they carry no policy/provenance
envelope. They follow the ``JobRow`` pattern: indexed/FK columns for the lookups the gate
needs, and the full protocol model in ``body`` (reconstructed via ``to_model``). Membership
is unique per (workspace, user) — a user holds at most one role in a workspace.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import BodyMixin, IdMixin, VersionMixin
from metis_core.db.types import TZDateTime


class OrganizationRow(Base, IdMixin, VersionMixin, BodyMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[TZDateTime] = mapped_column(index=True)


class UserRow(Base, IdMixin, VersionMixin, BodyMixin):
    __tablename__ = "users"

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    created_at: Mapped[TZDateTime] = mapped_column(index=True)


class WorkspaceRow(Base, IdMixin, VersionMixin, BodyMixin):
    __tablename__ = "workspaces"

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[TZDateTime] = mapped_column(index=True)


class WorkspaceMembershipRow(Base, IdMixin, VersionMixin, BodyMixin):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[TZDateTime] = mapped_column(index=True)


class WorkspaceModelPolicyRow(Base, VersionMixin, BodyMixin):
    """One row per workspace (keyed by workspace_id): its model-routing policy. Mutable config, so
    ``set`` upserts rather than insert-by-id like the append-only artifact stores."""

    __tablename__ = "workspace_model_policies"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    allow_external_models: Mapped[bool] = mapped_column(Boolean)
    daily_cost_cap_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
