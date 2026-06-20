"""Connector-backed sources and their sync state: the durable replacement for the gateway's
in-memory source registry.

A :class:`SourceConfig` is *what to ingest* — a connector bound to one workspace, with the
sensitivity floor its content inherits. A :class:`SourceCursor` is *where the last sync got to*,
so a re-poll after a restart surfaces only what is new. A :class:`ConnectorRun` is *what one pass
did*, the row the operator source dashboard and the ingestion-lag/failure signals read.

Like :class:`WorkspaceModelPolicy`, these are mutable operational config/state rather than audited
evidence artifacts, so they are not registered in the schema snapshot set.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, JsonValue

from metis_protocol.enums import ConnectorRunStatus, Sensitivity
from metis_protocol.ids import ConnectorRunId, SourceId, WorkspaceId
from metis_protocol.versioning import VersionedModel


class SourceCredentialRef(VersionedModel):
    """A pointer to a secret held in the encrypted credential store, never the secret itself.

    ``scheme`` is the connector's auth method (``basic``, ``oauth2``, …) and ``handle`` is the
    opaque name the credential store resolves at connect time, so a config can be listed, audited,
    and reasoned about without ever carrying a password or token.
    """

    scheme: str
    handle: str


class SourceConfig(VersionedModel):
    """A configured connector-backed source, bound to one workspace.

    The durable replacement for the gateway's in-memory source registry: source setup survives a
    restart and the ingest worker reads it to know what to poll. ``auth_method`` is resolved from
    the connector spec at registration; ``credential`` points at a secret without holding it; the
    ingested content inherits ``sensitivity`` as its floor.
    """

    id: SourceId
    workspace_id: WorkspaceId
    name: str
    connector: str
    sensitivity: Sensitivity
    auth_method: str
    credential: SourceCredentialRef | None = None
    created_at: AwareDatetime
    active: bool = True
    # Connector-specific selection (which mailbox/folder/chat): opaque to the protocol, validated by
    # the connector registry — e.g. a Telegram source's business-connection id + chat id.
    config: dict[str, JsonValue] = Field(default_factory=dict)


class SourceCursor(VersionedModel):
    """The durable resume point for a source's incremental sync.

    The connector's opaque cursor token plus when it last advanced — one row per source (keyed by
    ``source_id``), upserted as the worker makes progress so a re-poll after a restart resumes
    rather than re-ingests. ``cursor`` is ``None`` before the first successful pass.
    """

    source_id: SourceId
    cursor: str | None = None
    updated_at: AwareDatetime


class ConnectorRun(VersionedModel):
    """One audited pass of a connector over a source: when it ran, its outcome, and what it made.

    Opened ``RUNNING`` and closed ``SUCCEEDED``/``FAILED`` (the same id), so the operator source
    dashboard shows live sync state and history, and ingestion-lag/failure-rate signals build on
    these rows rather than on log scraping.
    """

    id: ConnectorRunId
    source_id: SourceId
    workspace_id: WorkspaceId
    status: ConnectorRunStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    artifacts: int = 0
    claims: int = 0
    error: str | None = None


class TelegramDiscoveredChat(VersionedModel):
    """A chat the bot has observed on a Business connection — surfaced for source selection.

    The Bot API has no "list authorized chats" call, so chats are discovered as messages arrive:
    one record per ``(business_connection_id, chat_id)``, upserted with the latest title + message
    as new messages come in, so an operator can pick which chats to ingest without knowing the
    numeric ids in advance. Operational discovery state, not evidence — like the cursors, it
    is not in the schema snapshot set.
    """

    business_connection_id: str
    chat_id: int
    chat_type: str
    title: str
    last_message_id: int = 0
    last_seen_at: AwareDatetime
