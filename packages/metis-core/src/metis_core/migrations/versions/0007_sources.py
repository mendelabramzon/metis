"""durable connector sources: configs, resume cursors, run history

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-19

Server-deployment Stage 1, Workstream 1.4/1.2 (durable source state): connector source configs,
their incremental-sync cursors, and connector-run history, so source setup and sync progress
survive a restart and the ingest worker resumes rather than re-ingests. Creates the three new
tables, like 0003–0006.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("source_configs", "source_cursors", "connector_runs")


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=_tables())
