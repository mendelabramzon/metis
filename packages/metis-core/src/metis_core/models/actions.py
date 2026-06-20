"""Proposed-action table: typed interpreted intents awaiting (or past) a risk-gated decision.

Operational state like ``JobRow``/``SourceConfigRow`` (no policy/provenance envelope) — just the
indexed columns the approval inbox queries on (``workspace_id``, ``kind``, ``status``), with the
full ``ProposedAction`` model in ``body``.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from metis_core.db.base import Base
from metis_core.db.mixins import BodyMixin, IdMixin, TimestampMixin, VersionMixin, WorkspaceMixin


class ProposedActionRow(Base, IdMixin, WorkspaceMixin, VersionMixin, TimestampMixin, BodyMixin):
    __tablename__ = "proposed_actions"

    kind: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(index=True)
