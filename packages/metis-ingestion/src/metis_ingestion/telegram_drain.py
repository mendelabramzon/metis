"""Dedicated Telegram drain: one global getUpdates queue per bot token, fanned out to every source.

Telegram's getUpdates is a single queue per bot token, so the worker drains it *once* per cycle and
ingests the batch into every active Telegram source — not one getUpdates per source, which would let
the per-chat sources steal each other's updates. The global offset advances per cycle so confirmed
updates drop; each source resumes from its durable message-id cursor, so a re-fetched backlog (after
a restart, before the offset is re-advanced) never re-ingests a seen message.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from metis_ingestion.connectors.telegram_bot_transport import TelegramBotClient
from metis_protocol import SourceConfig, TelegramDiscoveredChat

#: Ingest one source's chat from the drained batch (build its connector, resume its cursor, poll).
SyncSource = Callable[[SourceConfig, Sequence[Mapping[str, Any]]], Awaitable[None]]

#: Record the chats a batch surfaced (discovery), so an operator can pick which to ingest.
RecordChats = Callable[[Sequence[Mapping[str, Any]]], Awaitable[None]]


def extract_discovered_chats(updates: Sequence[Mapping[str, Any]]) -> list[TelegramDiscoveredChat]:
    """The distinct chats seen across a getUpdates batch, as discovery records to upsert.

    The Bot API has no "list authorized chats" call, so the drain records chats as their messages
    arrive — one record per (connection, chat), with the latest title + message id — and an operator
    lists these to pick which to ingest as sources. The latest message in the batch for a chat wins.
    """
    seen: dict[tuple[str, int], TelegramDiscoveredChat] = {}
    now = datetime.now(UTC)
    for update in updates:
        for key in ("business_message", "edited_business_message"):
            message = update.get(key)
            if not isinstance(message, Mapping):
                continue
            connection = message.get("business_connection_id")
            chat = message.get("chat")
            if not isinstance(connection, str) or not isinstance(chat, Mapping):
                continue
            chat_id = chat.get("id")
            if not isinstance(chat_id, int):
                continue
            title = chat.get("title") or chat.get("first_name") or chat.get("username")
            seen[(connection, chat_id)] = TelegramDiscoveredChat(
                business_connection_id=connection,
                chat_id=chat_id,
                chat_type=str(chat.get("type", "private")),
                title=str(title or f"chat {chat_id}"),
                last_message_id=int(message.get("message_id", 0)),
                last_seen_at=now,
            )
    return list(seen.values())


async def drain_telegram_once(
    *,
    client: TelegramBotClient,
    offset: int,
    sources: Sequence[SourceConfig],
    sync_source: SyncSource,
    record_chats: RecordChats | None = None,
) -> int:
    """Drain one getUpdates batch into every active source; return the offset for the next call.

    Returns ``offset`` unchanged when nothing new arrived, else ``max(update_id) + 1`` so the next
    call confirms (drops) this batch. ``record_chats`` (when given) records the batch's discovered
    chats first. The offset advances only after the whole batch is processed, so if anything raises
    the batch is re-fetched and the per-source cursors dedup it.
    """
    updates = client.get_updates(offset=offset)
    if not updates:
        return offset
    if record_chats is not None:
        await record_chats(updates)
    for source in sources:
        await sync_source(source, updates)
    return max(int(update["update_id"]) for update in updates) + 1
