"""memory retrieval indexes: pgvector HNSW + FTS GIN (Stage 5)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-18

Stage 5 fixes the embedding dimension (ADR 0014), which finally allows pgvector's HNSW
index to be built. The vector/FTS index DDL lives next to the lookup code in
``metis_core.memory_index.index_migrations``; this revision just applies it. The columns
themselves come from the ORM models via 0001's ``create_all`` — only the indexes are added
here.
"""

from __future__ import annotations

from alembic import op

from metis_core.memory_index.index_migrations import create_memory_indexes, drop_memory_indexes

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_memory_indexes(op.get_bind())


def downgrade() -> None:
    drop_memory_indexes(op.get_bind())
