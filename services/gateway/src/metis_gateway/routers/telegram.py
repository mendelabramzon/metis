"""Telegram chat discovery: list the chats the bot has seen on a Business connection.

The Bot API has no "list authorized chats" call, so the ingest worker records chats as their
messages arrive; this exposes them (operator-gated) so a chat can be turned into a source by its
id — the selection step before ``POST /sources`` with a ``telegram`` config.
"""

from __future__ import annotations

from fastapi import APIRouter

from metis_gateway.deps import BackendDep, OperatorDep
from metis_gateway.schemas import TelegramChatView

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/chats", response_model=list[TelegramChatView])
async def list_discovered_chats(
    backend: BackendDep, _principal: OperatorDep, connection: str | None = None
) -> list[TelegramChatView]:
    """Discovered chats, newest-seen first; filter to one connection with ``?connection=``."""
    chats = await backend.sources.list_discovered_chats(connection)
    return [
        TelegramChatView(
            business_connection_id=chat.business_connection_id,
            chat_id=chat.chat_id,
            chat_type=chat.chat_type,
            title=chat.title,
            last_message_id=chat.last_message_id,
        )
        for chat in chats
    ]
