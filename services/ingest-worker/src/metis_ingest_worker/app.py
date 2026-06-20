"""Entrypoint wiring for the ingest worker (ADR 0009).

``run()`` builds typed settings and wires a poller over the configured connector (a local folder or
an IMAP mailbox) and the core stores, then polls it on an interval — each cycle ingests what is new
and advances the cursor. When ``source_id`` names a registered source, the poll loop is durable
(``DurableIngestPoller``): it resumes from that source's stored cursor and records a connector run
per active cycle, so a restart resumes rather than re-ingests. ``--dry-run`` wires settings and
stops (no database needed), backing the boot test.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from metis_core.audit import PostgresAuditSink
from metis_core.config import CoreSettings
from metis_core.db.engine import make_engine, make_sessionmaker
from metis_core.jobs import PostgresJobQueue
from metis_core.llm import (
    AnthropicProvider,
    MetisModelRouter,
    ModelCaller,
    OpenAICompatProvider,
    RoutableProvider,
)
from metis_core.llm.ocr import model_transcriber
from metis_core.objectstore import S3ObjectStore
from metis_core.observability import setup_telemetry
from metis_core.security import Cryptobox
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
    PostgresSourceStore,
)
from metis_ingestion import (
    ConnectorSyncWorker,
    DurableIngestPoller,
    ImapConfig,
    ImapConnector,
    ImapTransport,
    IngestionPipeline,
    IngestPoller,
    LocalFolderConnector,
    OAuth2Client,
    OAuthTokens,
    build_gmail_connector,
    build_google_drive_connector,
)
from metis_ingestion.connectors import FetchingConnector
from metis_ingestion.poller import Pipeline
from metis_ingestion.security.cred_store import EncryptedCredentialStore
from metis_protocol import AuditSink, ModelTier, SourceConfig, SourceId, WorkspaceId

from .settings import IngestWorkerSettings


def _vision_caller(
    settings: IngestWorkerSettings, audit_sink: AuditSink
) -> tuple[ModelCaller | None, list[Callable[[], Awaitable[None]]]]:
    """A vision ModelCaller for scanned-PDF OCR (None if none configured), plus its client closers.

    Anthropic (cloud Claude vision) and/or a self-hosted OpenAI-compatible vision endpoint.
    """
    providers: list[RoutableProvider] = []
    closers: list[Callable[[], Awaitable[None]]] = []
    if settings.anthropic_api_key:
        import anthropic  # lazy: only when an Anthropic key is configured

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        closers.append(client.close)
        providers.append(AnthropicProvider(client))
    if settings.vision_endpoint and settings.vision_model:
        http = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        closers.append(http.aclose)
        providers.append(
            OpenAICompatProvider(
                http,
                name="ocr-vlm",
                model=settings.vision_model,
                is_external=settings.vision_external,
                tiers=(ModelTier.LOCAL,),
                base_url=f"{settings.vision_endpoint.rstrip('/')}/v1",
                supports_vision=True,
            )
        )
    if not providers:
        return None, []
    return ModelCaller(MetisModelRouter(providers), audit_sink), closers


logger = logging.getLogger("metis_ingest_worker")


def build_connector(
    settings: IngestWorkerSettings, workspace_id: WorkspaceId, *, connector: str | None = None
) -> FetchingConnector:
    """The connector to run, selected by ``connector`` (a source's type) or ``settings.connector``.

    Connector-specific params (mailbox host/credentials, the local root) still come from settings;
    wiring them fully from the SourceConfig + the credential store is a later slice.
    """
    connector = connector if connector is not None else settings.connector
    if connector == "imap":
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
    source_store = PostgresSourceStore(sessionmaker)

    # A registered source drives the workspace and gives the poll loop a durable cursor + run
    # history; absent one, fall back to the configured workspace with an in-process cursor.
    source = await source_store.get(SourceId(settings.source_id)) if settings.source_id else None
    if settings.source_id and source is None:
        raise ValueError(f"configured source {settings.source_id!r} is not registered")
    workspace_id = source.workspace_id if source is not None else WorkspaceId(settings.workspace_id)

    pipeline = IngestionPipeline(
        connector=build_connector(settings, workspace_id),
        artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
        document_store=PostgresDocumentStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
        source_id=source.id if source is not None else None,
    )
    poller: IngestPoller | DurableIngestPoller = (
        await DurableIngestPoller.resume(pipeline, source=source, store=source_store)
        if source is not None
        else IngestPoller(pipeline)
    )
    try:
        while True:
            result = await poller.poll_once()
            logger.info(
                "ingested %d artifact(s), %d claim(s), %d failure(s) (source=%s cursor=%s)",
                result.artifacts,
                result.claims,
                len(result.failures),
                settings.source_id or "-",
                poller.cursor,
            )
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await engine.dispose()


async def _drain_jobs(settings: IngestWorkerSettings, core: CoreSettings) -> None:
    """Lease ``ingest.poll`` jobs from the durable queue and run each source's sync (server path).

    Mirrors the maintainer worker: drain the queue, sleeping only when idle. ``ConnectorSyncWorker``
    completes a job on success and reschedules it with backoff on failure, and the durable cursor
    means a retry resumes where the sync left off rather than re-scanning.
    """
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
    sources = PostgresSourceStore(sessionmaker)
    artifact_store = PostgresMinioArtifactStore(sessionmaker, object_store)
    document_store = PostgresDocumentStore(sessionmaker)
    claim_store = PostgresClaimStore(sessionmaker)
    audit_sink = PostgresAuditSink(sessionmaker)
    # A vision caller for scanned-PDF OCR (None unless a vision model is configured); the per-source
    # transcriber binds the workspace so the router's policy gating applies.
    ocr_caller, ocr_closers = _vision_caller(settings, audit_sink)

    # OAuth + Drive use their own HTTP clients (async for the token endpoint, sync for the Drive API
    # snapshot); credentials come from the encrypted store, keyed by cred_store_key.
    token_http = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    drive_http = httpx.Client(timeout=httpx.Timeout(120.0))
    credentials = (
        EncryptedCredentialStore(Cryptobox(settings.cred_store_key))
        if settings.cred_store_key
        else None
    )

    async def connector_for(source: SourceConfig) -> FetchingConnector:
        if source.connector not in ("gdrive", "gmail"):
            return build_connector(settings, source.workspace_id, connector=source.connector)
        if credentials is None:
            raise ValueError(
                f"a {source.connector} source needs METIS_INGEST_WORKER_CRED_STORE_KEY set"
            )
        store = credentials  # non-None for the persist closure below
        resolver = store.for_connector(source.connector)  # Drive + Gmail share Google OAuth
        oauth = OAuth2Client(
            token_url=settings.google_token_url,
            client_id=settings.google_client_id,
            client_secret=resolver.resolve("client_secret"),
            http_client=token_http,
        )

        def _persist(tokens: OAuthTokens) -> None:
            store.set_credential(
                connector=source.connector, name="refresh_token", value=tokens.refresh_token
            )

        if source.connector == "gmail":
            labels = tuple(label for label in settings.gmail_label_ids.split(",") if label)
            return await build_gmail_connector(
                workspace_id=source.workspace_id,
                sensitivity=source.sensitivity,
                refresh_token=resolver.resolve("refresh_token"),
                oauth=oauth,
                gmail_http=drive_http,  # the sync Google-API client (shared with Drive)
                query=settings.gmail_query,
                label_ids=labels,
                user_id=settings.gmail_user_id,
                persist=_persist,
            )
        return await build_google_drive_connector(
            workspace_id=source.workspace_id,
            folder_id=settings.gdrive_folder_id,
            sensitivity=source.sensitivity,
            refresh_token=resolver.resolve("refresh_token"),
            oauth=oauth,
            drive_http=drive_http,
            persist=_persist,
        )

    async def pipeline_factory(source: SourceConfig) -> Pipeline:
        transcribe = (
            model_transcriber(ocr_caller, source.workspace_id) if ocr_caller is not None else None
        )
        return IngestionPipeline(
            connector=await connector_for(source),
            artifact_store=artifact_store,
            document_store=document_store,
            claim_store=claim_store,
            audit_sink=audit_sink,
            source_id=source.id,
            transcribe=transcribe,
        )

    worker = ConnectorSyncWorker(
        PostgresJobQueue(sessionmaker), sources=sources, pipeline_factory=pipeline_factory
    )
    try:
        while True:
            if await worker.run_once() == 0:
                await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await token_http.aclose()
        drive_http.close()
        for close in ocr_closers:
            await close()
        await engine.dispose()


def run(
    *, dry_run: bool = False, settings: IngestWorkerSettings | None = None
) -> IngestWorkerSettings:
    settings = settings if settings is not None else IngestWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    setup_telemetry("ingest-worker")  # no-op without an OTLP endpoint; resumes job traces
    logger.info(
        "metis-ingest-worker wiring (mode=%s, connector=%s, poll_interval_seconds=%s)",
        settings.mode,
        settings.connector,
        settings.poll_interval_seconds,
    )
    if dry_run:
        logger.info("dry run complete; not polling")
        return settings
    runner = _poll if settings.mode == "poll" else _drain_jobs
    asyncio.run(runner(settings, CoreSettings()))
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
