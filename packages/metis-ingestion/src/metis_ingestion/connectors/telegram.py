"""Telegram connector: render a chat's messages to markdown ``CHAT_MESSAGE`` artifacts.

The default (sanctioned) Telegram transport is a Business connected-bot: the account owner
authorizes specific chats and the bot receives their messages as updates (forward sync). Each
selected chat is its own source; within it, every message becomes its own ``CHAT_MESSAGE`` artifact
— like Gmail's per-message ingest — carrying sender, timestamp, reply/forward context, and
attachment references, so edits version one message and a deletion tombstones one message rather
than a whole conversation. Private chats and groups floor at ``CONFIDENTIAL`` so personal chatter
never renders below the connector's restricted-by-default sensitivity (a public channel keeps the
source's own level).

The connector is transport-agnostic: it reads a per-chat ``messages.json`` listing plus one
canonical message JSON per id, so the *same* code runs over a live bot transport or a
``RecordedTransport`` of fixtures (the credential-free replay path). The opt-in TDLib transport
(history backfill + followed channels) produces the same listing shape, so it plugs in unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field, TypeAdapter

from metis_ingestion import mime
from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, ConnectorError, RenderedPayload
from metis_ingestion.mime import MediaInfo
from metis_protocol import ArtifactKind, Sensitivity, SourceId, SourceRef, max_sensitivity

_LISTING_KEY = "messages.json"

#: Chat kinds whose content is private to its participants — floored above a public channel's.
_PRIVATE_CHAT_TYPES = frozenset({"private", "group", "supergroup"})


class TelegramSourceConfig(BaseModel):
    """The validated ``SourceConfig.config`` payload for a Telegram chat source.

    One selected chat per source: the Business connection that authorizes the bot to see it, the
    chat id, and its kind (which sets the sensitivity floor). The opt-in TDLib path fills the same
    shape with ``business_connection_id`` left empty.
    """

    business_connection_id: str = ""
    chat_id: int
    chat_type: str = "private"


class _Sender(BaseModel):
    id: int | None = None
    name: str = "unknown"
    username: str | None = None


class _Chat(BaseModel):
    id: int
    type: str = "private"  # private | group | supergroup | channel
    title: str = ""

    @property
    def is_private(self) -> bool:
        return self.type in _PRIVATE_CHAT_TYPES


class _Reply(BaseModel):
    """Just enough of the replied-to message to show thread context without re-fetching it."""

    message_id: int
    sender: str = "unknown"
    excerpt: str = ""


class _Forward(BaseModel):
    origin: str  # who or where the message was forwarded from


class _Media(BaseModel):
    kind: str  # photo | document | video | audio | voice | sticker | ...
    file_id: str = ""
    file_name: str | None = None
    mime_type: str | None = None
    caption: str | None = None


class _Message(BaseModel):
    """One Telegram message in canonical form — the shape every transport renders to."""

    message_id: int
    chat: _Chat
    date: int  # unix seconds
    sender: _Sender = Field(default_factory=_Sender)
    text: str = ""
    reply_to: _Reply | None = None
    forward_from: _Forward | None = None
    edited: bool = False
    media: tuple[_Media, ...] = ()


class _Entry(BaseModel):
    """A listing row: the message id, where its canonical JSON lives, and its sortable watermark."""

    id: str
    content_key: str
    cursor: str  # sortable per-chat watermark (a zero-padded message id), like Gmail's internalDate


_LISTING = TypeAdapter(tuple[_Entry, ...])


def _render_markdown(message: _Message) -> str:
    """A readable markdown rendering of one message — the bytes the pipeline parses like a note."""
    chat = message.chat
    when = datetime.fromtimestamp(message.date, tz=UTC).isoformat()
    edited = " · edited" if message.edited else ""
    lines = [
        f"# {chat.title or f'chat {chat.id}'} ({chat.type})",
        "",
        f"**{message.sender.name}** · {when}{edited}",
        "",
    ]
    context: list[str] = []
    if message.reply_to is not None:
        context.append(
            f"> In reply to {message.reply_to.sender}: {message.reply_to.excerpt}".rstrip()
        )
    if message.forward_from is not None:
        context.append(f"> Forwarded from {message.forward_from.origin}")
    if context:
        lines += [*context, ""]
    if message.text.strip():
        lines.append(message.text.strip())
    for item in message.media:
        label = item.file_name or item.file_id or item.kind
        detail = f" ({item.mime_type})" if item.mime_type else ""
        caption = f" — {item.caption}" if item.caption else ""
        lines.append(f"- {item.kind}: {label}{detail}{caption}")
    return "\n".join(lines).rstrip() + "\n"


class TelegramConnector(BaseConnector):
    connector = "telegram"

    def _listing(self) -> tuple[_Entry, ...]:
        return _LISTING.validate_json(self._read(_LISTING_KEY))

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for entry in self._listing():
            if cursor is not None and entry.cursor <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"telegram:{entry.id}"),
                    connector=self.connector,
                    locator=entry.id,
                    cursor=entry.cursor,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        for entry in self._listing():
            if entry.id == locator:
                message = _Message.model_validate_json(self._read(entry.content_key))
                floor = Sensitivity.CONFIDENTIAL if message.chat.is_private else Sensitivity.PUBLIC
                return RenderedPayload(
                    data=_render_markdown(message).encode("utf-8"),
                    media=MediaInfo(mime.MD, ArtifactKind.CHAT_MESSAGE),
                    policy=self._policy(max_sensitivity(self._sensitivity, floor)),
                )
        raise ConnectorError(f"unknown telegram message {locator!r}")
