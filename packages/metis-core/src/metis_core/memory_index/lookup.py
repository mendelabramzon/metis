"""The memory index lookup primitive: hybrid vector + FTS search with rank fusion.

This is the read counterpart to :mod:`metis_core.memory_index.embeddings`. It runs two
rankers over the same scope — approximate nearest-neighbour over the pgvector column and
Postgres full-text search over the same ``to_tsvector`` expression the GIN index uses —
and fuses them with Reciprocal Rank Fusion (RRF). Hybrid retrieval is more robust than
either ranker alone: vectors catch paraphrase, FTS catches exact terms/identifiers.

Only memory objects that match the query's embedding *version* are vector-eligible, so a
re-index never compares vectors across models (ADR 0014). Superseded/retracted/tombstoned
cells are excluded, mirroring the store's default-query semantics.

This is a primitive, not the ``Retriever`` protocol: the policy-bound, query-rewriting
``Retriever`` that composes it (and wiki/graph retrieval) is runtime-owned in Stage 8.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.mixins import EmbeddedArtifactRow
from metis_core.mappers import to_model
from metis_core.memory_index.embeddings import Embedded, EmbeddingRouter
from metis_core.memory_index.index_migrations import MEM_FTS_SQL, SCENE_FTS_SQL, SEGMENT_FTS_SQL
from metis_core.models import MemCellRow, MemSceneRow, SegmentRow
from metis_protocol import (
    MemCell,
    MemScene,
    Segment,
    Sensitivity,
    VersionedModel,
    WorkspaceId,
)

#: RRF damping constant. 60 is the value from the original RRF paper; larger values flatten
#: the contribution of top ranks, smaller values sharpen it.
DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class Hit[M: VersionedModel]:
    """A retrieved item with its fused score and its rank in each ranker (``None`` = absent)."""

    item: M
    score: float
    vector_rank: int | None
    fts_rank: int | None


def rrf_fuse(rankings: Sequence[Sequence[str]], *, k: int = DEFAULT_RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: ``score(id) = sum_rankers 1 / (k + rank)`` (rank 0-based)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, identifier in enumerate(ranking):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + position + 1)
    return scores


class MemoryIndexLookup:
    """Hybrid lookup over MemCells, MemScenes, and (for the naive baseline) Segments."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        router: EmbeddingRouter,
        *,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._router = router
        self._rrf_k = rrf_k

    async def search_mem_cells(
        self,
        *,
        workspace_id: WorkspaceId,
        query_text: str,
        k: int = 10,
        candidates: int = 50,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> list[Hit[MemCell]]:
        embedded = await self._router.embed_one(query_text, sensitivity=sensitivity)
        async with self._sessionmaker() as session:
            return await self._search(
                session,
                row_type=MemCellRow,
                model_type=MemCell,
                live=(
                    MemCellRow.workspace_id == str(workspace_id),
                    MemCellRow.retracted.is_(False),
                    MemCellRow.superseded.is_(False),
                    MemCellRow.tombstoned_at.is_(None),
                ),
                fts_sql=MEM_FTS_SQL,
                query_text=query_text,
                embedded=embedded,
                k=k,
                candidates=candidates,
            )

    async def search_scenes(
        self,
        *,
        workspace_id: WorkspaceId,
        query_text: str,
        k: int = 10,
        candidates: int = 50,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> list[Hit[MemScene]]:
        embedded = await self._router.embed_one(query_text, sensitivity=sensitivity)
        async with self._sessionmaker() as session:
            return await self._search(
                session,
                row_type=MemSceneRow,
                model_type=MemScene,
                live=(
                    MemSceneRow.workspace_id == str(workspace_id),
                    MemSceneRow.tombstoned_at.is_(None),
                ),
                fts_sql=SCENE_FTS_SQL,
                query_text=query_text,
                embedded=embedded,
                k=k,
                candidates=candidates,
            )

    async def search_segments(
        self,
        *,
        workspace_id: WorkspaceId,
        query_text: str,
        k: int = 10,
        candidates: int = 50,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> list[Hit[Segment]]:
        """Naive-RAG baseline: the same hybrid search, but over raw chunks instead of memory."""
        embedded = await self._router.embed_one(query_text, sensitivity=sensitivity)
        async with self._sessionmaker() as session:
            return await self._search(
                session,
                row_type=SegmentRow,
                model_type=Segment,
                live=(
                    SegmentRow.workspace_id == str(workspace_id),
                    SegmentRow.tombstoned_at.is_(None),
                ),
                fts_sql=SEGMENT_FTS_SQL,
                query_text=query_text,
                embedded=embedded,
                k=k,
                candidates=candidates,
            )

    async def _search[M: VersionedModel](
        self,
        session: AsyncSession,
        *,
        row_type: type[EmbeddedArtifactRow],
        model_type: type[M],
        live: tuple[ColumnElement[bool], ...],
        fts_sql: str,
        query_text: str,
        embedded: Embedded,
        k: int,
        candidates: int,
    ) -> list[Hit[M]]:
        # Vector ranker: nearest by cosine distance, restricted to the query's embedding
        # version so we never compare across embedding models.
        vector_stmt = (
            select(row_type.id)
            .where(
                *live,
                row_type.embedding.is_not(None),
                row_type.embedding_version == embedded.version,
            )
            .order_by(row_type.embedding.cosine_distance(embedded.vectors[0]))
            .limit(candidates)
        )
        vector_ids = list((await session.scalars(vector_stmt)).all())

        # FTS ranker: the doc expression is the verbatim index expression, so the GIN
        # index is eligible; the query string is bound (never interpolated).
        tsvector = func.to_tsvector("english", text(fts_sql))
        tsquery = func.plainto_tsquery("english", query_text)
        fts_stmt = (
            select(row_type.id)
            .where(*live, tsvector.op("@@")(tsquery))
            .order_by(func.ts_rank(tsvector, tsquery).desc())
            .limit(candidates)
        )
        fts_ids = list((await session.scalars(fts_stmt)).all())

        scores = rrf_fuse([vector_ids, fts_ids], k=self._rrf_k)
        ordered = sorted(scores, key=lambda identifier: scores[identifier], reverse=True)[:k]
        rows = {
            row.id: row
            for row in (
                await session.scalars(select(row_type).where(row_type.id.in_(ordered)))
            ).all()
        }
        vector_pos = {identifier: position for position, identifier in enumerate(vector_ids)}
        fts_pos = {identifier: position for position, identifier in enumerate(fts_ids)}
        return [
            Hit(
                item=to_model(rows[identifier], model_type),
                score=scores[identifier],
                vector_rank=vector_pos.get(identifier),
                fts_rank=fts_pos.get(identifier),
            )
            for identifier in ordered
            if identifier in rows
        ]
