"""Dedicated Telegram drain: one global getUpdates queue per bot token, fanned out to every source.

Telegram's getUpdates is a single queue per bot token, so the worker drains it *once* per cycle and
ingests the batch into every active Telegram source — not one getUpdates per source, which would let
the per-chat sources steal each other's updates. The global offset advances per cycle so confirmed
updates drop; each source resumes from its durable message-id cursor, so a re-fetched backlog (after
a restart, before the offset is re-advanced) never re-ingests a seen message.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from metis_ingestion.connectors.telegram_bot_transport import TelegramBotClient
from metis_protocol import SourceConfig

#: Ingest one source's chat from the drained batch (build its connector, resume its cursor, poll).
SyncSource = Callable[[SourceConfig, Sequence[Mapping[str, Any]]], Awaitable[None]]


async def drain_telegram_once(
    *,
    client: TelegramBotClient,
    offset: int,
    sources: Sequence[SourceConfig],
    sync_source: SyncSource,
) -> int:
    """Drain one getUpdates batch into every active source; return the offset for the next call.

    Returns ``offset`` unchanged when nothing new arrived, else ``max(update_id) + 1`` so the next
    call confirms (drops) this batch. The offset advances only after the whole batch is ingested, so
    if a ``sync_source`` raises the batch is re-fetched and the per-source cursors dedup it.
    """
    updates = client.get_updates(offset=offset)
    if not updates:
        return offset
    for source in sources:
        await sync_source(source, updates)
    return max(int(update["update_id"]) for update in updates) + 1
