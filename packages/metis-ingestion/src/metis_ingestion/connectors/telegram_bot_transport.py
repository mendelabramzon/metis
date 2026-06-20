"""A live Telegram ``Transport``: convert Business connected-bot updates into a per-chat snapshot.

The connector spine (``base``) expects a synchronous ``Transport`` (``list_keys`` + ``read``) over a
fixed set of responses — here a ``messages.json`` listing plus one canonical message JSON per id,
exactly the shape ``TelegramConnector`` reads from recorded fixtures. This transport builds that
shape from a batch of Bot API updates: it keeps the ``business_message`` and
``edited_business_message`` updates for *this* source's connection + chat, maps each to a canonical
message form (sender, timestamp, reply/forward context, attachments), and collects
``deleted_business_messages`` ids for the worker to tombstone.

Updates are handed in, not fetched here: the bot's getUpdates stream is one global queue per token,
so the worker drains it once (advancing the global offset) and fans the batch out to each chat's
transport. :class:`TelegramBotClient` is the thin live getUpdates call the worker uses; it is
injected an HTTP client, so the suite drives it against a fake with no live Telegram. Per-chat
idempotency comes from the connector's message-id cursor, so re-processing a batch never re-ingests
a seen one, and a re-rendered edit is a new content-addressed artifact (a new version of a message).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from metis_ingestion.connectors.base import ConnectorError
from metis_ingestion.connectors.telegram import TelegramConnector, TelegramSourceConfig
from metis_protocol import Sensitivity, WorkspaceId

_LISTING_KEY = "messages.json"
_CURSOR_WIDTH = 12  # zero-pad message ids so the connector's string cursor sorts numerically

#: The update kinds a Business connected-bot needs for forward sync (passed to getUpdates).
BUSINESS_UPDATES: tuple[str, ...] = (
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
)


@dataclass(frozen=True)
class TelegramBotConfig:
    """Which chat this transport ingests: the owner's Business connection + the chat id."""

    business_connection_id: str
    chat_id: int


def _chat_title(chat: Mapping[str, Any]) -> str:
    if chat.get("title"):
        return str(chat["title"])
    name = " ".join(str(p) for p in (chat.get("first_name"), chat.get("last_name")) if p)
    return name or (f"@{chat['username']}" if chat.get("username") else f"chat {chat.get('id')}")


def _person_name(person: Mapping[str, Any]) -> str:
    if person.get("title"):  # a channel/group acting as sender
        return _chat_title(person)
    name = " ".join(str(p) for p in (person.get("first_name"), person.get("last_name")) if p)
    return name or (f"@{person['username']}" if person.get("username") else "unknown")


def _forward_origin(message: Mapping[str, Any]) -> dict[str, str] | None:
    origin = message.get("forward_origin")
    if not isinstance(origin, Mapping):
        return None
    kind = origin.get("type")
    if kind == "user" and isinstance(origin.get("sender_user"), Mapping):
        return {"origin": _person_name(origin["sender_user"])}
    if kind in ("chat", "channel"):
        chat = origin.get("chat") or origin.get("sender_chat")
        if isinstance(chat, Mapping):
            return {"origin": _chat_title(chat)}
    if kind == "hidden_user" and origin.get("sender_user_name"):
        return {"origin": str(origin["sender_user_name"])}
    return {"origin": "unknown"}


_MEDIA_FIELDS = ("document", "video", "audio", "voice", "animation", "sticker")


def _extract_media(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    caption = message.get("caption")
    photo = message.get("photo")
    if isinstance(photo, Sequence) and photo:
        largest = photo[-1]  # a PhotoSize list, ascending by resolution
        media.append({"kind": "photo", "file_id": largest.get("file_id", ""), "caption": caption})
    for kind in _MEDIA_FIELDS:
        item = message.get(kind)
        if isinstance(item, Mapping):
            media.append(
                {
                    "kind": kind,
                    "file_id": item.get("file_id", ""),
                    "file_name": item.get("file_name"),
                    "mime_type": item.get("mime_type"),
                    "caption": caption,
                }
            )
    return media


def _to_canonical(message: Mapping[str, Any], *, edited: bool) -> dict[str, Any]:
    """Map a Bot API ``Message`` to the canonical shape ``TelegramConnector`` renders."""
    chat = message.get("chat", {})
    sender = message.get("from") or message.get("sender_chat") or {}
    canonical: dict[str, Any] = {
        "message_id": message["message_id"],
        "chat": {
            "id": chat.get("id"),
            "type": chat.get("type", "private"),
            "title": _chat_title(chat),
        },
        "date": message.get("date", 0),
        "sender": {
            "id": sender.get("id"),
            "name": _person_name(sender),
            "username": sender.get("username"),
        },
        "text": message.get("text") or message.get("caption") or "",
        "edited": edited,
        "media": _extract_media(message),
    }
    reply = message.get("reply_to_message")
    if isinstance(reply, Mapping):
        canonical["reply_to"] = {
            "message_id": reply.get("message_id"),
            "sender": _person_name(reply.get("from", {})),
            "excerpt": (reply.get("text") or reply.get("caption") or "")[:120],
        }
    forward = _forward_origin(message)
    if forward is not None:
        canonical["forward_from"] = forward
    return canonical


@dataclass
class _Snapshot:
    listing: bytes
    content: dict[str, bytes]
    deleted: tuple[str, ...]


class TelegramBotTransport:
    """A live Telegram ``Transport`` — a per-chat snapshot built from a batch of bot updates."""

    def __init__(self, config: TelegramBotConfig, *, updates: Sequence[Mapping[str, Any]]) -> None:
        self._config = config
        self._updates = updates
        self._snapshot: _Snapshot | None = None

    def _mine(self, message: Any) -> Mapping[str, Any] | None:
        """``message`` if it belongs to this source's connection and chat, else ``None``."""
        if not isinstance(message, Mapping):
            return None
        if message.get("business_connection_id") != self._config.business_connection_id:
            return None
        chat = message.get("chat", {})
        return message if chat.get("id") == self._config.chat_id else None

    def _deletions(self, update: Mapping[str, Any]) -> list[str]:
        deleted = update.get("deleted_business_messages")
        if not isinstance(deleted, Mapping):
            return []
        if deleted.get("business_connection_id") != self._config.business_connection_id:
            return []
        if deleted.get("chat", {}).get("id") != self._config.chat_id:
            return []
        return [f"{self._config.chat_id}:{mid}" for mid in deleted.get("message_ids", [])]

    def _load(self) -> _Snapshot:
        if self._snapshot is not None:
            return self._snapshot
        content: dict[str, bytes] = {}
        entries: list[dict[str, str]] = []
        seen: set[int] = set()
        deleted: list[str] = []
        for update in self._updates:
            for key, edited in (("business_message", False), ("edited_business_message", True)):
                message = self._mine(update.get(key))
                if message is None:
                    continue
                mid = int(message["message_id"])
                content_key = f"content/{self._config.chat_id}-{mid}.json"
                content[content_key] = json.dumps(_to_canonical(message, edited=edited)).encode()
                if (
                    mid not in seen
                ):  # an edit shares the id; list the message once, newest content wins
                    seen.add(mid)
                    entries.append(
                        {
                            "id": f"{self._config.chat_id}:{mid}",
                            "content_key": content_key,
                            "cursor": f"{mid:0{_CURSOR_WIDTH}d}",
                        }
                    )
            deleted.extend(self._deletions(update))
        entries.sort(key=lambda entry: entry["cursor"])
        self._snapshot = _Snapshot(
            listing=json.dumps(entries).encode(), content=content, deleted=tuple(deleted)
        )
        return self._snapshot

    def list_keys(self, prefix: str = "") -> Sequence[str]:
        snapshot = self._load()
        keys = [_LISTING_KEY, *sorted(snapshot.content)]
        return [k for k in keys if k.startswith(prefix)] if prefix else keys

    def read(self, key: str) -> bytes:
        snapshot = self._load()
        if key == _LISTING_KEY:
            return snapshot.listing
        try:
            return snapshot.content[key]
        except KeyError as exc:
            raise ConnectorError(f"no Telegram message {key!r}") from exc

    @property
    def deleted_message_ids(self) -> tuple[str, ...]:
        """Ids (``chat:message``) the connection deleted here — for the worker to tombstone."""
        return self._load().deleted


class TelegramBotClient:
    """The live Bot API getUpdates call — the bot's one global update queue, faked in tests.

    Injected a sync HTTP client (``.get(url, params)`` -> ``.json()``), like the Gmail transport.
    The worker calls ``get_updates`` once per drain with the global ``offset`` (last update id + 1)
    and fans the batch out to each chat's :class:`TelegramBotTransport`.
    """

    def __init__(
        self,
        *,
        token: str,
        http_client: Any,
        base_url: str = "https://api.telegram.org",
        timeout: int = 0,
    ) -> None:
        self._token = token
        self._http = http_client
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def get_updates(
        self, *, offset: int = 0, allowed_updates: Sequence[str] = BUSINESS_UPDATES
    ) -> list[dict[str, Any]]:
        response = self._http.get(
            f"{self._base}/bot{self._token}/getUpdates",
            params={
                "offset": offset,
                "timeout": self._timeout,
                "allowed_updates": json.dumps(list(allowed_updates)),
            },
        ).json()
        if not response.get("ok", False):
            raise ConnectorError(
                f"getUpdates failed: {response.get('description', 'unknown error')}"
            )
        return list(response.get("result", []))


def build_telegram_connector(
    *,
    workspace_id: WorkspaceId,
    config: TelegramSourceConfig,
    sensitivity: Sensitivity,
    updates: Sequence[Mapping[str, Any]],
) -> TelegramConnector:
    """Build the Telegram connector for one chat source over a batch of drained bot updates.

    ``config`` is the validated per-chat selection (a source's ``config`` payload); ``updates`` is
    the batch the worker drained from getUpdates. The connector renders this source's new/edited
    messages to CHAT_MESSAGE artifacts; the transport's ``deleted_message_ids`` drive tombstones.
    """
    transport = TelegramBotTransport(
        TelegramBotConfig(
            business_connection_id=config.business_connection_id, chat_id=config.chat_id
        ),
        updates=updates,
    )
    return TelegramConnector(
        workspace_id=workspace_id, transport=transport, sensitivity=sensitivity
    )
