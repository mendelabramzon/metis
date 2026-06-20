"""connector secrets

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-21

Server-deployment Stage 1 (operational): a durable, encrypted-at-rest home for connector secrets
(OAuth refresh tokens, Telegram TDLib database-encryption keys) so a secret the gateway writes is
readable by the ingest worker and survives a restart — both processes share this one table. Creates
the one new table, like 0003–0009.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("connector_secrets",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
