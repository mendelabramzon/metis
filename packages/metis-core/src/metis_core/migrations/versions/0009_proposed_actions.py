"""proposed actions

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-20

Server-deployment Stage 1, Workstream 1.5 (command/proposed-action surface): durable proposed
actions — the typed intent the system understood a free-text request as — persisted before any
effectful execution, with the human decision recorded. Creates the one new table, like 0003–0008.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("proposed_actions",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
