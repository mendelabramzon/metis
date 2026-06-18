"""Column mixins so every table inherits id/workspace/version/policy/timestamps/body
consistently. ``provenance`` and ``policy`` live inside ``body``; ``workspace_id`` and
``sensitivity`` are denormalized into indexed columns for tenancy and policy queries.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.types import Body, Id, TZDateTime


class IdMixin:
    id: Mapped[Id] = mapped_column(primary_key=True)


class WorkspaceMixin:
    workspace_id: Mapped[Id] = mapped_column(index=True)


class VersionMixin:
    schema_version: Mapped[str] = mapped_column()


class PolicyMixin:
    # Denormalized from body["policy"]["sensitivity"] for policy-scoped queries.
    sensitivity: Mapped[str] = mapped_column(index=True)


class TimestampMixin:
    created_at: Mapped[TZDateTime] = mapped_column(index=True)


class TombstoneMixin:
    tombstoned_at: Mapped[TZDateTime | None] = mapped_column()


class BodyMixin:
    # The full protocol model dump; the row is reconstructed by validating it.
    body: Mapped[Body] = mapped_column()


class ArtifactRow(
    IdMixin,
    WorkspaceMixin,
    VersionMixin,
    PolicyMixin,
    TimestampMixin,
    TombstoneMixin,
    BodyMixin,
):
    """Common columns shared by every stored artifact table."""
