"""Source tables: connector configs, their resume cursors, and connector-run history.

Operational config/state, not evidence artifacts, so (like ``JobRow``) they carry no
policy/provenance envelope — just the indexed columns the worker and the operator dashboard
query on, with the full protocol model in ``body``. ``workspace_id`` is a denormalized indexed
column (not a FK), matching the artifact tables: a source is scoped to its configured workspace,
which need not be an identity-table row.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import BodyMixin, IdMixin, TimestampMixin, VersionMixin, WorkspaceMixin
from metis_core.db.types import Id, TZDateTime


class SourceConfigRow(Base, IdMixin, WorkspaceMixin, VersionMixin, TimestampMixin, BodyMixin):
    __tablename__ = "source_configs"

    connector: Mapped[str] = mapped_column(index=True)
    active: Mapped[bool] = mapped_column(Boolean, index=True)


class SourceCursorRow(Base, VersionMixin, BodyMixin):
    """One row per source (keyed by ``source_id``): its incremental-sync resume point. Mutable, so
    the store upserts rather than insert-by-id like the append-only artifact stores."""

    __tablename__ = "source_cursors"

    source_id: Mapped[Id] = mapped_column(primary_key=True)
    updated_at: Mapped[TZDateTime] = mapped_column(index=True)


class ConnectorRunRow(Base, IdMixin, WorkspaceMixin, VersionMixin, BodyMixin):
    __tablename__ = "connector_runs"

    source_id: Mapped[Id] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(index=True)
    started_at: Mapped[TZDateTime] = mapped_column(index=True)


class TelegramChatRow(Base, VersionMixin, BodyMixin):
    """One chat discovered on a Business connection (keyed by connection + chat), upserted as
    messages arrive — the operator's source-selection candidates. Operational state, no envelope."""

    __tablename__ = "telegram_chats"

    business_connection_id: Mapped[str] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_seen_at: Mapped[TZDateTime] = mapped_column(index=True)
