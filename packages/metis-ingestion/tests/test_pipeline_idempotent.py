"""Ingesting a folder twice produces one logical artifact set and no duplicate facts."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.models import ClaimRow, RawArtifactRow
from metis_ingestion import IngestionPipeline


async def _count(sessionmaker: async_sessionmaker[AsyncSession], model: object) -> int:
    async with sessionmaker() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_ingest_is_idempotent(
    sample_dir: Path,
    make_pipeline: Callable[[Path], IngestionPipeline],
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    pipeline = make_pipeline(sample_dir)

    first = await pipeline.run()
    assert first.artifacts == 8
    assert not first.failures
    claims = await _count(sessionmaker, ClaimRow)
    artifacts = await _count(sessionmaker, RawArtifactRow)
    assert claims > 0
    assert artifacts == 8

    second = await pipeline.run()
    assert second.artifacts == first.artifacts
    assert await _count(sessionmaker, ClaimRow) == claims  # no duplicate logical facts
    assert await _count(sessionmaker, RawArtifactRow) == artifacts
