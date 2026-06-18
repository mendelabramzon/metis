"""Entrypoint wiring for the ingest worker (ADR 0009).

``run()`` builds typed settings and wires the ingestion pipeline over the core
stores. ``--dry-run`` wires settings and stops (no database needed), backing the
boot test. A real (non-dry-run) invocation ingests the configured folder once.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from metis_core.audit import PostgresAuditSink
from metis_core.config import CoreSettings
from metis_core.db.engine import make_engine, make_sessionmaker
from metis_core.objectstore import S3ObjectStore
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
)
from metis_ingestion import IngestionPipeline, IngestResult, LocalFolderConnector
from metis_protocol import WorkspaceId

from .settings import IngestWorkerSettings

logger = logging.getLogger("metis_ingest_worker")


async def _ingest(worker: IngestWorkerSettings, core: CoreSettings) -> IngestResult:
    engine = make_engine(core.database_url)
    sessionmaker = make_sessionmaker(engine)
    object_store = S3ObjectStore(
        bucket=core.object_store_bucket,
        endpoint_url=core.object_store_endpoint_url,
        region=core.object_store_region,
        access_key=core.object_store_access_key,
        secret_key=core.object_store_secret_key,
    )
    await object_store.ensure_bucket()
    pipeline = IngestionPipeline(
        connector=LocalFolderConnector(
            worker.ingest_root, workspace_id=WorkspaceId(worker.workspace_id)
        ),
        artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
        document_store=PostgresDocumentStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
    )
    try:
        return await pipeline.run()
    finally:
        await engine.dispose()


def run(
    *, dry_run: bool = False, settings: IngestWorkerSettings | None = None
) -> IngestWorkerSettings:
    settings = settings if settings is not None else IngestWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    logger.info("metis-ingest-worker wiring (ingest_root=%s)", settings.ingest_root)
    if dry_run:
        logger.info("dry run complete; not ingesting")
        return settings
    result = asyncio.run(_ingest(settings, CoreSettings()))
    logger.info(
        "ingested %d artifacts, %d claims, %d failures",
        result.artifacts,
        result.claims,
        len(result.failures),
    )
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-ingest-worker")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="wire settings and exit without ingesting",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
