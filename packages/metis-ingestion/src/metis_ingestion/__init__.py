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
    GoogleDriveConnector,
    ImapConfig,
    ImapConnector,
    ImapTransport,
    InMemorySecretResolver,
    LocalFolderConnector,
    RateLimiter,
    RecordedTransport,
    SlackConnector,
    WebClipConnector,
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
from metis_ingestion.normalize import build_normalized_doc
from metis_ingestion.parsers import Segmentation, get_format, supported_media_types
from metis_ingestion.pipeline import IngestionPipeline, IngestResult
from metis_ingestion.poller import DurableIngestPoller, IngestPoller
from metis_ingestion.raw import build_raw_artifact
from metis_ingestion.segment import parse_document

__version__ = "0.0.0"

__all__ = [
    "BaselineExtractor",
    "CalendarConnector",
    "ConnectorRegistry",
    "ConnectorScheduler",
    "DurableIngestPoller",
    "ExtractError",
    "ExtractionResult",
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
    "ParseError",
    "RateLimiter",
    "RecordedTransport",
    "Segmentation",
    "SlackConnector",
    "StepFailure",
    "UnsupportedMediaType",
    "WebClipConnector",
    "__version__",
    "build_normalized_doc",
    "build_raw_artifact",
    "get_format",
    "mime",
    "parse_document",
    "supported_media_types",
    "with_retries",
]
