"""Seed the local dev database with the protocol example artifacts.

uv run python -m metis_core.dev.seed
"""

from __future__ import annotations

import asyncio

from metis_core.config import CoreSettings
from metis_core.db.engine import make_engine, make_sessionmaker
from metis_core.objectstore import S3ObjectStore
from metis_core.stores import PostgresMinioArtifactStore
from metis_protocol.examples import raw_artifact


async def _seed(settings: CoreSettings) -> None:
    engine = make_engine(settings.database_url)
    object_store = S3ObjectStore(
        bucket=settings.object_store_bucket,
        endpoint_url=settings.object_store_endpoint_url,
        region=settings.object_store_region,
        access_key=settings.object_store_access_key,
        secret_key=settings.object_store_secret_key,
    )
    await object_store.ensure_bucket()
    store = PostgresMinioArtifactStore(make_sessionmaker(engine), object_store)
    ref = await store.put(raw_artifact())
    await engine.dispose()
    print(f"seeded raw artifact {ref.artifact_id}")


def main() -> int:
    asyncio.run(_seed(CoreSettings()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
