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
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
from metis_core.security import Cryptobox, PostgresSecretStore
from metis_core.security.deletion import erase_artifacts_by_filename
from metis_core.security.secrets import SecretNotFoundError
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
    NativeTdjsonClient,
    OAuth2Client,
    OAuthTokens,
    TelegramBotClient,
    TelegramSourceConfig,
    build_gmail_connector,
    build_google_drive_connector,
    build_tdlib_connector,
    build_telegram_connector,
    drain_tdlib_once,
    drain_telegram_once,
    extract_discovered_chats,
)
from metis_ingestion.connectors import (
    AuthState,
    FetchingConnector,
    TdlibParameters,
    TelegramSession,
    TelegramTdlibClient,
    load_tdjson_library,
)
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


def _credentials(
    settings: IngestWorkerSettings, core: CoreSettings
) -> EncryptedCredentialStore | None:
    """The durable, shared credential store (Postgres) — the worker reads secrets the gateway wrote
    (OAuth refresh tokens, TDLib db keys). None when no cred store key is configured."""
    if not settings.cred_store_key:
        return None
    return EncryptedCredentialStore(
        store=PostgresSecretStore(core.database_url, Cryptobox(settings.cred_store_key))
    )


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
    credentials = _credentials(settings, core)

    async def connector_for(source: SourceConfig) -> FetchingConnector:
        if source.connector == "telegram":
            raise ValueError(
                "telegram sources sync via the telegram drain (mode=telegram), not poll jobs"
            )
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


async def _drain_telegram(settings: IngestWorkerSettings, core: CoreSettings) -> None:
    """Drain the Telegram bot's getUpdates queue and ingest each active Telegram source's chat.

    getUpdates is one global queue per bot token, so this drains once per cycle and fans the batch
    out to every active Telegram source — a per-source poll job can't, as the chats would steal each
    other's updates. Each source resumes from its durable message-id cursor, so a re-fetched backlog
    (after a restart, before the offset re-advances) is deduped rather than re-ingested.
    """
    if not settings.telegram_bot_token:
        raise ValueError("telegram mode needs METIS_INGEST_WORKER_TELEGRAM_BOT_TOKEN set")
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
    ocr_caller, ocr_closers = _vision_caller(settings, audit_sink)
    http = httpx.Client(timeout=httpx.Timeout(settings.telegram_timeout_seconds + 30.0))
    client = TelegramBotClient(
        token=settings.telegram_bot_token,
        http_client=http,
        base_url=settings.telegram_base_url,
        timeout=int(settings.telegram_timeout_seconds),
    )

    async def sync_source(source: SourceConfig, updates: Sequence[Mapping[str, Any]]) -> None:
        config = TelegramSourceConfig.model_validate(source.config)
        transcribe = (
            model_transcriber(ocr_caller, source.workspace_id) if ocr_caller is not None else None
        )
        connector = build_telegram_connector(
            workspace_id=source.workspace_id,
            config=config,
            sensitivity=source.sensitivity,
            updates=updates,
        )
        pipeline = IngestionPipeline(
            connector=connector,
            artifact_store=artifact_store,
            document_store=document_store,
            claim_store=claim_store,
            audit_sink=audit_sink,
            source_id=source.id,
            transcribe=transcribe,
        )
        poller = await DurableIngestPoller.resume(pipeline, source=source, store=sources)
        await poller.poll_once()
        # A message deleted in this chat tombstones its own artifact + derived claims.
        if connector.deleted_message_ids:
            await erase_artifacts_by_filename(
                sessionmaker,
                object_store,
                workspace_id=str(source.workspace_id),
                source_id=str(source.id),
                filenames=connector.deleted_message_ids,
            )

    async def record_chats(updates: Sequence[Mapping[str, Any]]) -> None:
        for chat in extract_discovered_chats(updates):
            await sources.upsert_discovered_chat(chat)

    async def deactivate_revoked(connection_ids: set[str]) -> None:
        """Pause the sources of any Business connection the owner revoked (they can't sync now)."""
        for source in await sources.list_all():
            if source.connector != "telegram" or not source.active:
                continue
            connection = TelegramSourceConfig.model_validate(source.config).business_connection_id
            if connection and connection in connection_ids:
                await sources.set_active(source.id, False)
                logger.warning(
                    "telegram: connection %s revoked; paused source %s", connection, source.id
                )

    offset = 0
    try:
        while True:
            # Bot sources carry a business connection; TDLib sources (a tdlib_user_id, no
            # connection) are backfilled by the telegram_tdlib drain, not the bot's getUpdates.
            active = [
                s
                for s in await sources.list_all()
                if s.connector == "telegram"
                and s.active
                and TelegramSourceConfig.model_validate(s.config).business_connection_id
            ]
            offset = await drain_telegram_once(
                client=client,
                offset=offset,
                sources=active,
                sync_source=sync_source,
                record_chats=record_chats,
                on_revoked=deactivate_revoked,
            )
            logger.info("telegram drain: %d active source(s), next offset=%d", len(active), offset)
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        http.close()
        for close in ocr_closers:
            await close()
        await engine.dispose()


async def _drain_tdlib(settings: IngestWorkerSettings, core: CoreSettings) -> None:
    """Backfill the opt-in TDLib sources: per account, reopen its authorized session + page history.

    TDLib sources are the Telegram sources carrying a ``tdlib_user_id`` (vs. the bot path's business
    connection). Each account's db-encryption key comes from the cred store; the worker reopens that
    authorized TDLib database (a shared volume the gateway login created), drives the session to
    READY, and backfills each chat through the same per-chat connector/cursor as the bot path.
    Backfill is read-only history, so there are no deletions to tombstone.
    """
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise ValueError("telegram_tdlib mode needs METIS_INGEST_WORKER_TELEGRAM_API_ID/HASH set")
    if not settings.cred_store_key:
        raise ValueError("telegram_tdlib mode needs METIS_INGEST_WORKER_CRED_STORE_KEY set")
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
    ocr_caller, ocr_closers = _vision_caller(settings, audit_sink)
    credentials = _credentials(settings, core)
    assert credentials is not None  # cred_store_key is required for this mode (guarded above)

    @contextmanager
    def account_sessions(user_id: str) -> Iterator[TelegramTdlibClient | None]:
        """Open one account's authorized backfill client (None if missing or unauthorized)."""
        try:
            db_key = credentials.for_connector("telegram_tdlib").resolve(f"db_key:{user_id}")
        except SecretNotFoundError:
            logger.warning("telegram_tdlib: no stored db key for account %s; skipping", user_id)
            yield None
            return
        params = TdlibParameters(
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            database_directory=str(Path(settings.telegram_tdlib_data_root) / user_id),
            database_encryption_key=db_key,
        )
        client = NativeTdjsonClient(load_tdjson_library(settings.telegram_tdlib_library or None))
        session = TelegramSession(client=client, parameters=params)
        if session.pump(poll_timeout=settings.telegram_tdlib_poll_seconds) is not AuthState.READY:
            logger.warning("telegram_tdlib: account %s did not authorize; skipping", user_id)
            client.close()
            yield None
            return
        try:
            yield TelegramTdlibClient(client)
        finally:
            client.close()  # release the handle so the account's database is free next cycle

    async def sync_source(
        source: SourceConfig,
        messages: Sequence[Mapping[str, Any]],
        users: Mapping[int, Mapping[str, Any]],
        chats: Mapping[int, Mapping[str, Any]],
    ) -> None:
        config = TelegramSourceConfig.model_validate(source.config)
        transcribe = (
            model_transcriber(ocr_caller, source.workspace_id) if ocr_caller is not None else None
        )
        connector = build_tdlib_connector(
            workspace_id=source.workspace_id,
            config=config,
            sensitivity=source.sensitivity,
            messages=messages,
            users=users,
            chats=chats,
        )
        pipeline = IngestionPipeline(
            connector=connector,
            artifact_store=artifact_store,
            document_store=document_store,
            claim_store=claim_store,
            audit_sink=audit_sink,
            source_id=source.id,
            transcribe=transcribe,
        )
        poller = await DurableIngestPoller.resume(pipeline, source=source, store=sources)
        await poller.poll_once()

    try:
        while True:
            synced = await drain_tdlib_once(
                sources=await sources.list_all(),
                account_sessions=account_sessions,
                sync_source=sync_source,
                page_size=settings.telegram_tdlib_page_size,
                max_pages=settings.telegram_tdlib_max_pages,
            )
            logger.info("telegram_tdlib backfill: %d source(s) synced", synced)
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
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
    runners = {"poll": _poll, "telegram": _drain_telegram, "telegram_tdlib": _drain_tdlib}
    runner = runners.get(settings.mode, _drain_jobs)
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
