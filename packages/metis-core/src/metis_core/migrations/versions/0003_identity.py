"""identity and tenancy: organizations, users, workspaces, memberships

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19

Server-deployment Stage 1 introduces first-class identity. The columns come from the ORM
models (registered on ``Base.metadata`` by importing ``metis_core.models``); this revision
creates just the four new identity tables — 0001 built the rest — so it touches nothing else.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("organizations", "users", "workspaces", "workspace_memberships")


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=list(reversed(_tables())))
