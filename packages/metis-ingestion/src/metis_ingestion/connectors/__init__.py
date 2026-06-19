"""Source connectors: one uniform contract (``RawArtifact`` + ``NormalizedDoc``) over every source.

Stage 3 shipped the local-folder connector; Stage 11 adds remote sources (IMAP/email, Slack,
web clip, Google Drive, calendar) on a shared spine (``base``) that handles artifact construction,
normalization, cursors, rate limiting, retry/backoff, and a recorded-response transport for
credential-free replay. ``auth`` names secrets without holding them, ``registry`` resolves
connectors by name, and ``scheduling`` turns polls/webhooks into core ingest jobs. Connector shapes
never escape past ``NormalizedDoc`` — the contract that keeps downstream stages connector-agnostic.
"""

from __future__ import annotations

from metis_ingestion.connectors.auth import (
    AuthMethod,
    ConnectorAuth,
    InMemorySecretResolver,
    SecretResolver,
    basic_auth,
    no_auth,
    oauth2,
    token_auth,
)
from metis_ingestion.connectors.base import (
    AuthError,
    BaseConnector,
    ConnectorError,
    FetchingConnector,
    RateLimiter,
    RateLimitError,
    RecordedTransport,
    RenderedPayload,
    TransientError,
    Transport,
    source_policy,
    with_retries,
)
from metis_ingestion.connectors.calendar import CalendarConnector
from metis_ingestion.connectors.drive_transport import DriveConfig, DriveTransport
from metis_ingestion.connectors.gdrive import GoogleDriveConnector
from metis_ingestion.connectors.imap import ImapConnector
from metis_ingestion.connectors.imap_transport import ImapConfig, ImapTransport
from metis_ingestion.connectors.local_folder import LocalFolderConnector
from metis_ingestion.connectors.oauth import (
    OAuth2Client,
    OAuthTokens,
    RefreshingTokenProvider,
    TokenProvider,
)
from metis_ingestion.connectors.registry import (
    ConnectorRegistry,
    ConnectorSpec,
    UnknownConnectorError,
)
from metis_ingestion.connectors.scheduling import (
    POLL_JOB_KIND,
    WEBHOOK_JOB_KIND,
    ConnectorScheduler,
    WebhookVerificationError,
    build_poll_job,
    build_webhook_job,
    poll_due,
)
from metis_ingestion.connectors.slack import SlackConnector
from metis_ingestion.connectors.web_clip import WebClipConnector

__all__ = [
    "POLL_JOB_KIND",
    "WEBHOOK_JOB_KIND",
    "AuthError",
    "AuthMethod",
    "BaseConnector",
    "CalendarConnector",
    "ConnectorAuth",
    "ConnectorError",
    "ConnectorRegistry",
    "ConnectorScheduler",
    "ConnectorSpec",
    "DriveConfig",
    "DriveTransport",
    "FetchingConnector",
    "GoogleDriveConnector",
    "ImapConfig",
    "ImapConnector",
    "ImapTransport",
    "InMemorySecretResolver",
    "LocalFolderConnector",
    "OAuth2Client",
    "OAuthTokens",
    "RateLimitError",
    "RateLimiter",
    "RecordedTransport",
    "RefreshingTokenProvider",
    "RenderedPayload",
    "SecretResolver",
    "SlackConnector",
    "TokenProvider",
    "TransientError",
    "Transport",
    "UnknownConnectorError",
    "WebClipConnector",
    "WebhookVerificationError",
    "basic_auth",
    "build_poll_job",
    "build_webhook_job",
    "no_auth",
    "oauth2",
    "poll_due",
    "source_policy",
    "token_auth",
    "with_retries",
]
