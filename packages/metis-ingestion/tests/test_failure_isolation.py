"""A corrupt file is recorded as a failure and does not stop sibling artifacts."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.models import ClaimRow
from metis_ingestion import IngestionPipeline


async def test_corrupt_file_does_not_stop_siblings(
    tmp_path: Path,
    make_pipeline: Callable[[Path], IngestionPipeline],
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    (tmp_path / "good.txt").write_text("Ada Lovelace is the CTO of Acme Inc.")
    (tmp_path / "broken.pdf").write_bytes(b"definitely not a pdf at all")

    result = await make_pipeline(tmp_path).run()

    assert result.artifacts == 1  # only good.txt fully ingested
    assert len(result.failures) == 1
    assert result.failures[0].locator == "broken.pdf"

    async with sessionmaker() as session:
        claims = (await session.execute(select(func.count()).select_from(ClaimRow))).scalar_one()
    assert claims > 0  # the good sibling produced evidence
