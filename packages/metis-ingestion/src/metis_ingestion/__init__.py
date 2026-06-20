"""metis-ingestion: turn sources into structured, source-cited evidence.

Pipeline: discover -> fetch -> store raw -> normalize -> parse -> segment ->
extract -> write evidence. Produces evidence and extraction batches only — never
memory cells or wiki pages.
"""

from __future__ import annotations

from metis_ingestion import mime
from metis_ingestion.connectors import (
    CalendarConnector,
    ConnectorRegistry,
    ConnectorScheduler,
    DriveConfig,
    DriveTransport,
    GmailConfig,
    GmailConnector,
    GmailTransport,
    GoogleDriveConnector,
    ImapConfig,
    ImapConnector,
    ImapTransport,
    InMemorySecretResolver,
    LocalFolderConnector,
    OAuth2Client,
    OAuthTokens,
    RateLimiter,
    RecordedTransport,
    RefreshingTokenProvider,
    SlackConnector,
    TelegramBotClient,
    TelegramSourceConfig,
    TokenProvider,
    WebClipConnector,
    build_gmail_connector,
    build_google_drive_connector,
    build_tdlib_connector,
    build_telegram_connector,
    with_retries,
)
from metis_ingestion.extract import BaselineExtractor, ExtractionResult
from metis_ingestion.failures import (
    ExtractError,
    IngestionError,
    ParseError,
    StepFailure,
    UnsupportedMediaType,
)
from metis_ingestion.normalize import build_normalized_doc, build_normalized_doc_rich
from metis_ingestion.parsers import (
    ParseProduct,
    ParseQuality,
    Segmentation,
    assess,
    get_format,
    supported_media_types,
)
from metis_ingestion.pipeline import IngestionPipeline, IngestResult
from metis_ingestion.poller import DurableIngestPoller, IngestPoller
from metis_ingestion.raw import build_raw_artifact
from metis_ingestion.segment import parse_document
from metis_ingestion.sync_worker import ConnectorSyncWorker
from metis_ingestion.telegram_drain import drain_telegram_once, extract_discovered_chats

__version__ = "0.0.0"

__all__ = [
    "BaselineExtractor",
    "CalendarConnector",
    "ConnectorRegistry",
    "ConnectorScheduler",
    "ConnectorSyncWorker",
    "DriveConfig",
    "DriveTransport",
    "DurableIngestPoller",
    "ExtractError",
    "ExtractionResult",
    "GmailConfig",
    "GmailConnector",
    "GmailTransport",
    "GoogleDriveConnector",
    "ImapConfig",
    "ImapConnector",
    "ImapTransport",
    "InMemorySecretResolver",
    "IngestPoller",
    "IngestResult",
    "IngestionError",
    "IngestionPipeline",
    "LocalFolderConnector",
    "OAuth2Client",
    "OAuthTokens",
    "ParseError",
    "ParseProduct",
    "ParseQuality",
    "RateLimiter",
    "RecordedTransport",
    "RefreshingTokenProvider",
    "Segmentation",
    "SlackConnector",
    "StepFailure",
    "TelegramBotClient",
    "TelegramSourceConfig",
    "TokenProvider",
    "UnsupportedMediaType",
    "WebClipConnector",
    "__version__",
    "assess",
    "build_gmail_connector",
    "build_google_drive_connector",
    "build_normalized_doc",
    "build_normalized_doc_rich",
    "build_raw_artifact",
    "build_tdlib_connector",
    "build_telegram_connector",
    "drain_telegram_once",
    "extract_discovered_chats",
    "get_format",
    "mime",
    "parse_document",
    "supported_media_types",
    "with_retries",
]
