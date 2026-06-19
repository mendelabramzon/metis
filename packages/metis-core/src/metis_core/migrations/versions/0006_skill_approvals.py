"""durable skill-approval queue

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-19

Server-deployment Stage 1, Workstream 1.5 (durable state): the skill-approval queue, so an
outbound/destructive run held for human approval survives a restart. One new table, like 0003-0005.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("skill_approvals",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
