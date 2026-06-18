"""The pgvector + FTS index DDL for memory retrieval, co-located with the lookup code.

These indexes could not be declared in Stage 2 because pgvector's HNSW index requires
a fixed vector dimension, which was only nailed down once an embedding model was chosen
(ADR 0014). They are therefore created by a dedicated migration (0002) rather than by the
``create_all`` in 0001, and the canonical DDL lives here so it sits next to the queries
in :mod:`metis_core.memory_index.lookup` that depend on it.

Two index families per searchable table:

- an **HNSW** index with ``vector_cosine_ops`` for approximate nearest-neighbour search
  over the (now fixed-dimension) embedding column;
- a **GIN** index over the same ``to_tsvector`` expression the lookup uses for FTS, so
  the expression index is actually hit.

The FTS expression must match the lookup's expression verbatim or Postgres won't use the
index; :data:`MEM_FTS_SQL` / :data:`SEGMENT_FTS_SQL` are the single source of truth for both.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

# FTS documents per table. Each is used verbatim by both the GIN index here and the
# ``to_tsvector`` in the lookup query — they must stay byte-identical or Postgres won't
# use the expression index.
#: A mem cell's searchable text: its summary plus its narrative content.
MEM_FTS_SQL = "coalesce(body ->> 'summary', '') || ' ' || coalesce(body ->> 'content', '')"
#: A scene's searchable text: its title plus its rollup summary.
SCENE_FTS_SQL = "coalesce(body ->> 'title', '') || ' ' || coalesce(body ->> 'summary', '')"
#: A segment (chunk)'s searchable text: its raw text. Mirrors ``ix_segments_fts`` semantics.
SEGMENT_FTS_SQL = "coalesce(body ->> 'text', '')"

# (index name, DDL) pairs. CREATE/DROP use IF [NOT] EXISTS so the migration is idempotent
# and safe to re-run; 0001's create_all does not emit any of these.
_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "ix_mem_cells_embedding_hnsw",
        "CREATE INDEX IF NOT EXISTS ix_mem_cells_embedding_hnsw "
        "ON mem_cells USING hnsw (embedding vector_cosine_ops)",
    ),
    (
        "ix_mem_cells_fts",
        f"CREATE INDEX IF NOT EXISTS ix_mem_cells_fts "
        f"ON mem_cells USING gin (to_tsvector('english', {MEM_FTS_SQL}))",
    ),
    (
        "ix_mem_scenes_embedding_hnsw",
        "CREATE INDEX IF NOT EXISTS ix_mem_scenes_embedding_hnsw "
        "ON mem_scenes USING hnsw (embedding vector_cosine_ops)",
    ),
    (
        "ix_mem_scenes_fts",
        f"CREATE INDEX IF NOT EXISTS ix_mem_scenes_fts "
        f"ON mem_scenes USING gin (to_tsvector('english', {SCENE_FTS_SQL}))",
    ),
    (
        "ix_segments_embedding_hnsw",
        "CREATE INDEX IF NOT EXISTS ix_segments_embedding_hnsw "
        "ON segments USING hnsw (embedding vector_cosine_ops)",
    ),
)


def create_memory_indexes(connection: Connection) -> None:
    """Create every memory/segment retrieval index (idempotent)."""
    for _, ddl in _INDEXES:
        connection.execute(text(ddl))


def drop_memory_indexes(connection: Connection) -> None:
    """Drop every index created by :func:`create_memory_indexes` (idempotent)."""
    for name, _ in reversed(_INDEXES):
        connection.execute(text(f"DROP INDEX IF EXISTS {name}"))
