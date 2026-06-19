"""Entrypoint wiring for the ingest worker (ADR 0009).

``run()`` builds typed settings and wires an ``IngestPoller`` over the configured connector (a local
folder or an IMAP mailbox) and the core stores, then polls it on an interval — each cycle ingests
what is new and advances the cursor. ``--dry-run`` wires settings and stops (no database needed),
backing the boot test.
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
from metis_ingestion import (
    ImapConfig,
    ImapConnector,
    ImapTransport,
    IngestionPipeline,
    IngestPoller,
    LocalFolderConnector,
)
from metis_ingestion.connectors import FetchingConnector
from metis_protocol import WorkspaceId

from .settings import IngestWorkerSettings

logger = logging.getLogger("metis_ingest_worker")


def build_connector(settings: IngestWorkerSettings, workspace_id: WorkspaceId) -> FetchingConnector:
    """The connector the worker polls, selected by ``settings.connector``."""
    if settings.connector == "imap":
        config = ImapConfig(
            host=settings.imap_host,
            username=settings.imap_username,
            password=settings.imap_password,
            mailbox=settings.imap_mailbox,
        )
        return ImapConnector(workspace_id=workspace_id, transport=ImapTransport(config))
    return LocalFolderConnector(settings.ingest_root, workspace_id=workspace_id)


async def _poll(settings: IngestWorkerSettings, core: CoreSettings) -> None:
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
    poller = IngestPoller(
        IngestionPipeline(
            connector=build_connector(settings, WorkspaceId(settings.workspace_id)),
            artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
            document_store=PostgresDocumentStore(sessionmaker),
            claim_store=PostgresClaimStore(sessionmaker),
            audit_sink=PostgresAuditSink(sessionmaker),
        )
    )
    try:
        while True:
            result = await poller.poll_once()
            logger.info(
                "ingested %d artifact(s), %d claim(s), %d failure(s) (cursor=%s)",
                result.artifacts,
                result.claims,
                len(result.failures),
                poller.cursor,
            )
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await engine.dispose()


def run(
    *, dry_run: bool = False, settings: IngestWorkerSettings | None = None
) -> IngestWorkerSettings:
    settings = settings if settings is not None else IngestWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    logger.info(
        "metis-ingest-worker wiring (connector=%s, poll_interval_seconds=%s)",
        settings.connector,
        settings.poll_interval_seconds,
    )
    if dry_run:
        logger.info("dry run complete; not polling")
        return settings
    asyncio.run(_poll(settings, CoreSettings()))
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-ingest-worker")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="wire settings and exit without polling",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
