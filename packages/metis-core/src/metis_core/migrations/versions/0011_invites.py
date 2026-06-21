"""invites: single-use links to join an org + shared workspace

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-21

Adds the ``invites`` table (token-keyed, redeemed-once) so a workspace admin can mint an invite
link and an invitee can redeem it into a provisioned user + personal workspace + membership. The
columns come from the ORM model registered on ``Base.metadata`` by importing ``metis_core.models``.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Table

import metis_core.models  # noqa: F401  (registers tables on Base.metadata)
from metis_core.db.base import Base

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_TABLE_NAMES = ("invites",)


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in _TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=_tables())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=list(reversed(_tables())))
