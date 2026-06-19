"""durable wiki patch review queue

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-19

Server-deployment Stage 1, Workstream 1.5 (durable state): the wiki patch approval queue, so
proposed patches awaiting human review survive a restart. Creates just the one new table, like 0003/0004.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("wiki_patch_reviews",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
