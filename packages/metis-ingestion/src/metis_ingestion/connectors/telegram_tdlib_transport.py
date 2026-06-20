"""The opt-in TDLib Telegram ``Transport``: page a chat's message *history* into a chat snapshot.

This is the personal-account path for the two things the Business connected-bot cannot do — history
backfill (messages from before the bot was connected) and followed channels the user does not
administer. It sits behind the *same* ``Transport`` seam as the bot path: it produces the identical
``messages.json`` listing + one canonical message JSON per id that :class:`TelegramConnector` reads,
so per-chat ``SourceConfig``, cursoring, and erasure are unchanged — only the message *source*
differs (TDLib's ``getChatHistory`` instead of the bot's getUpdates).

TDLib messages are shaped differently from the Bot API: a sender is an id (resolved to a name via
``getUser``/``getChat``), text lives in a ``formattedText``, and content is tagged by ``@type``;
this module maps that to the canonical form. The native ``libtdjson`` is never imported here; the
live client (:mod:`telegram_session`) hands in already-fetched messages + the user/chat lookups it
resolved, so the transport — and the whole replay suite — runs with no native library and no live
account, exactly like the bot transport runs against a fake HTTP client.
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
# TDLib message ids are large (the Bot API id shifted left by 20 bits), so pad wide enough that the
# string cursor still sorts numerically. TDLib and bot ids are distinct id spaces — a chat should be
# synced by one transport (TDLib is the opt-in backfill path), so the two never share a cursor.
_CURSOR_WIDTH = 20

_MEDIA_CONTENT: dict[str, str] = {
    "messageDocument": "document",
    "messageVideo": "video",
    "messageAudio": "audio",
    "messageVoiceNote": "voice",
    "messageAnimation": "animation",
    "messageSticker": "sticker",
}

_CHAT_TYPES: dict[str, str] = {
    "chatTypePrivate": "private",
    "chatTypeBasicGroup": "group",
    "chatTypeSupergroup": "supergroup",  # refined to "channel" when the supergroup is a channel
    "chatTypeSecret": "private",
}


@dataclass(frozen=True)
class TelegramTdlibConfig:
    """Which chat this transport backfills: the chat id, plus its kind/title as a fallback when the
    chat object was not resolved (``business_connection_id`` is empty on the TDLib path)."""

    chat_id: int
    chat_type: str = "private"
    chat_title: str = ""


def _formatted_text(value: Any) -> str:
    """A TDLib ``formattedText`` -> its plain string (TDLib nests the text under ``.text``)."""
    return str(value["text"]) if isinstance(value, Mapping) and value.get("text") else ""


def _user_name(user: Mapping[str, Any]) -> str:
    name = " ".join(str(p) for p in (user.get("first_name"), user.get("last_name")) if p)
    username = user.get("username") or (user.get("usernames") or {}).get("editable_username")
    return name or (f"@{username}" if username else f"user {user.get('id')}")


def _chat_title(chat: Mapping[str, Any]) -> str:
    return str(chat.get("title") or f"chat {chat.get('id')}")


def _sender_name(
    sender_id: Any, users: Mapping[int, Mapping[str, Any]], chats: Mapping[int, Mapping[str, Any]]
) -> str:
    if not isinstance(sender_id, Mapping):
        return "unknown"
    if sender_id.get("@type") == "messageSenderUser":
        uid = sender_id.get("user_id")
        user = users.get(uid) if uid is not None else None
        return _user_name(user) if user is not None else f"user {uid}"
    if sender_id.get("@type") == "messageSenderChat":
        cid = sender_id.get("chat_id")
        chat = chats.get(cid) if cid is not None else None
        return _chat_title(chat) if chat is not None else f"chat {cid}"
    return "unknown"


def _sender_username(sender_id: Any, users: Mapping[int, Mapping[str, Any]]) -> str | None:
    if isinstance(sender_id, Mapping) and sender_id.get("@type") == "messageSenderUser":
        uid = sender_id.get("user_id")
        user = users.get(uid) if isinstance(uid, int) else None
        if user is not None:
            name = user.get("username") or (user.get("usernames") or {}).get("editable_username")
            return str(name) if name else None
    return None


def _sender_id_value(sender_id: Any) -> int | None:
    if isinstance(sender_id, Mapping):
        value = sender_id.get("user_id") if "user_id" in sender_id else sender_id.get("chat_id")
        return int(value) if isinstance(value, int) else None
    return None


def _remote_id(file: Any) -> str:
    """The stable remote id of a TDLib ``file`` (what survives across sessions)."""
    if isinstance(file, Mapping) and isinstance(file.get("remote"), Mapping):
        return str(file["remote"].get("id", ""))
    return ""


def _largest_photo(photo: Any) -> Any:
    sizes = photo.get("sizes") if isinstance(photo, Mapping) else None
    return sizes[-1].get("photo") if isinstance(sizes, Sequence) and sizes else None


def _text_and_media(content: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """A TDLib ``MessageContent`` -> (display text, canonical media list)."""
    kind = content.get("@type")
    if kind == "messageText":
        return _formatted_text(content.get("text")), []
    caption = _formatted_text(content.get("caption"))
    if kind == "messagePhoto":
        file = _largest_photo(content.get("photo"))
        return caption, [{"kind": "photo", "file_id": _remote_id(file), "caption": caption or None}]
    media_kind = _MEDIA_CONTENT.get(str(kind))
    if media_kind is not None:
        item = content.get(media_kind, {})
        file_key = "voice_note" if media_kind == "voice" else media_kind
        return caption, [
            {
                "kind": media_kind,
                "file_id": _remote_id(item.get(file_key) or item.get("document")),
                "file_name": item.get("file_name"),
                "mime_type": item.get("mime_type"),
                "caption": caption or None,
            }
        ]
    return caption, []  # an unsupported content type renders as its caption (often empty)


def _forward_name(
    message: Mapping[str, Any],
    users: Mapping[int, Mapping[str, Any]],
    chats: Mapping[int, Mapping[str, Any]],
) -> str | None:
    info = message.get("forward_info")
    origin = info.get("origin") if isinstance(info, Mapping) else None
    if not isinstance(origin, Mapping):
        return None
    kind = origin.get("@type")
    if kind == "messageForwardOriginUser":
        uid = origin.get("sender_user_id")
        user = users.get(uid) if isinstance(uid, int) else None
        return _user_name(user) if user is not None else "unknown"
    if kind in ("messageForwardOriginChat", "messageForwardOriginChannel"):
        cid = origin.get("sender_chat_id") or origin.get("chat_id")
        chat = chats.get(cid) if isinstance(cid, int) else None
        return _chat_title(chat) if chat is not None else "unknown"
    if kind == "messageForwardOriginHiddenUser":
        return str(origin.get("sender_name") or "unknown")
    return "unknown"


def _reply_message_id(message: Mapping[str, Any]) -> int | None:
    reply = message.get("reply_to")
    if isinstance(reply, Mapping) and reply.get("@type") == "messageReplyToMessage":
        mid = reply.get("message_id")
        return int(mid) if isinstance(mid, int) else None
    legacy = message.get("reply_to_message_id")
    return int(legacy) if isinstance(legacy, int) and legacy else None


@dataclass
class _Snapshot:
    listing: bytes
    content: dict[str, bytes]


class TelegramTdlibTransport:
    """A TDLib ``Transport`` — a per-chat snapshot built from a page of history messages."""

    def __init__(
        self,
        config: TelegramTdlibConfig,
        *,
        messages: Sequence[Mapping[str, Any]],
        users: Mapping[int, Mapping[str, Any]] | None = None,
        chats: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> None:
        self._config = config
        self._messages = messages
        self._users = users or {}
        self._chats = chats or {}
        self._snapshot: _Snapshot | None = None

    def _chat_descriptor(self) -> dict[str, Any]:
        chat = self._chats.get(self._config.chat_id)
        if chat is None:
            return {
                "id": self._config.chat_id,
                "type": self._config.chat_type,
                "title": self._config.chat_title,
            }
        chat_type = chat.get("type", {})
        kind = _CHAT_TYPES.get(str(chat_type.get("@type")), self._config.chat_type)
        if kind == "supergroup" and chat_type.get("is_channel"):
            kind = "channel"
        return {"id": self._config.chat_id, "type": kind, "title": _chat_title(chat)}

    def _to_canonical(
        self, message: Mapping[str, Any], *, excerpts: Mapping[int, tuple[str, str]]
    ) -> dict[str, Any]:
        text, media = _text_and_media(message.get("content", {}))
        sender_id = message.get("sender_id")
        canonical: dict[str, Any] = {
            "message_id": int(message["id"]),
            "chat": self._chat_descriptor(),
            "date": int(message.get("date", 0)),
            "sender": {
                "id": _sender_id_value(sender_id),
                "name": _sender_name(sender_id, self._users, self._chats),
                "username": _sender_username(sender_id, self._users),
            },
            "text": text,
            "edited": int(message.get("edit_date", 0)) > 0,
            "media": media,
        }
        reply_id = _reply_message_id(message)
        if reply_id is not None:
            sender, excerpt = excerpts.get(reply_id, ("unknown", ""))
            canonical["reply_to"] = {
                "message_id": reply_id,
                "sender": sender,
                "excerpt": excerpt[:120],
            }
        forward = _forward_name(message, self._users, self._chats)
        if forward is not None:
            canonical["forward_from"] = {"origin": forward}
        return canonical

    def _load(self) -> _Snapshot:
        if self._snapshot is not None:
            return self._snapshot
        mine = [m for m in self._messages if m.get("chat_id") == self._config.chat_id]
        # First pass: id -> (sender name, text) so a reply can quote the message it answers.
        excerpts: dict[int, tuple[str, str]] = {}
        for message in mine:
            text, _ = _text_and_media(message.get("content", {}))
            excerpts[int(message["id"])] = (
                _sender_name(message.get("sender_id"), self._users, self._chats),
                text,
            )
        content: dict[str, bytes] = {}
        entries: list[dict[str, str]] = []
        seen: set[int] = set()
        for message in mine:
            mid = int(message["id"])
            content_key = f"content/{self._config.chat_id}-{mid}.json"
            content[content_key] = json.dumps(
                self._to_canonical(message, excerpts=excerpts)
            ).encode()
            if mid not in seen:  # a re-fetched edit shares the id; list once, newest content wins
                seen.add(mid)
                entries.append(
                    {
                        "id": f"{self._config.chat_id}:{mid}",
                        "content_key": content_key,
                        "cursor": f"{mid:0{_CURSOR_WIDTH}d}",
                    }
                )
        entries.sort(key=lambda entry: entry["cursor"])
        self._snapshot = _Snapshot(listing=json.dumps(entries).encode(), content=content)
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


def build_tdlib_connector(
    *,
    workspace_id: WorkspaceId,
    config: TelegramSourceConfig,
    sensitivity: Sensitivity,
    messages: Sequence[Mapping[str, Any]],
    users: Mapping[int, Mapping[str, Any]] | None = None,
    chats: Mapping[int, Mapping[str, Any]] | None = None,
) -> TelegramConnector:
    """Build the Telegram connector for one chat source over a page of TDLib history.

    ``config`` is the same validated per-chat selection the bot path uses
    (``business_connection_id`` is empty on this path); ``messages`` is a page of TDLib ``message``
    objects, and ``users``/``chats`` the lookups the client resolved. The connector renders this
    source's messages to CHAT_MESSAGE artifacts exactly as it does for the bot transport.
    """
    transport = TelegramTdlibTransport(
        TelegramTdlibConfig(chat_id=config.chat_id, chat_type=config.chat_type),
        messages=messages,
        users=users,
        chats=chats,
    )
    return TelegramConnector(
        workspace_id=workspace_id, transport=transport, sensitivity=sensitivity
    )
