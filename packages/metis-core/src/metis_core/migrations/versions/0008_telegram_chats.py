"""telegram discovered chats

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-20

Server-deployment Stage 1, Workstream 1.4 (Telegram chat discovery): the chats the bot observes on a
Business connection, upserted as messages arrive, so an operator can pick which to ingest as sources.
Creates the one new table, like 0003–0007.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("telegram_chats",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
