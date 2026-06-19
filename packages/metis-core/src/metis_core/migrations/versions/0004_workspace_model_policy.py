"""per-workspace model policy table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19

Server-deployment Stage 1, Workstream 1.3: a per-workspace model-routing policy (external-model
allowance + an optional daily spend cap). Creates just the one new table, like 0003.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("workspace_model_policies",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
