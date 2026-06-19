"""Assemble a live Google Drive connector: resolve an access token, then build over the transport.

The Drive API reads behind the connector are synchronous (the ``Transport`` seam), but obtaining an
access token from the stored refresh token is async (it may hit the OAuth token endpoint). This
helper bridges the two: it resolves the token *once per build* — refreshing and persisting through
:class:`RefreshingTokenProvider` — then hands the already-resolved token to the sync
:class:`DriveTransport`, exactly as ``ImapConfig`` holds an already-resolved password. The worker
calls it from its async ``pipeline_factory`` before a sync begins.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from metis_ingestion.connectors.drive_transport import DriveConfig, DriveTransport
from metis_ingestion.connectors.gdrive import GoogleDriveConnector
from metis_ingestion.connectors.oauth import OAuth2Client, OAuthTokens, RefreshingTokenProvider
from metis_protocol import Sensitivity, WorkspaceId


async def build_google_drive_connector(
    *,
    workspace_id: WorkspaceId,
    folder_id: str,
    sensitivity: Sensitivity,
    refresh_token: str,
    oauth: OAuth2Client,
    drive_http: Any,
    persist: Callable[[OAuthTokens], None] | None = None,
    base_url: str | None = None,
) -> GoogleDriveConnector:
    """Resolve an access token from ``refresh_token`` and build the connector over a live transport.

    ``oauth`` carries the token endpoint + client credentials (its own async HTTP client);
    ``drive_http`` is the sync client the Drive API snapshot reads through. ``persist`` stores a
    rotated refresh token back (the encrypted credential store, in production).
    """
    provider = RefreshingTokenProvider.from_refresh_token(
        oauth=oauth, refresh_token=refresh_token, persist=persist
    )
    access_token = await provider.access_token()
    config = (
        DriveConfig(folder_id=folder_id)
        if base_url is None
        else DriveConfig(folder_id=folder_id, base_url=base_url)
    )
    transport = DriveTransport(config, access_token=access_token, http_client=drive_http)
    return GoogleDriveConnector(
        workspace_id=workspace_id, transport=transport, sensitivity=sensitivity
    )
