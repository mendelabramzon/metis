"""GET /telegram/chats lists the chats the bot discovered (operator-gated). The ingest worker
records them as messages arrive; here a chat is seeded directly to assert projection + auth.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from metis_protocol import TelegramDiscoveredChat


def _seed(client, *, connection: str, chat_id: int, title: str) -> None:
    chat = TelegramDiscoveredChat(
        business_connection_id=connection,
        chat_id=chat_id,
        chat_type="private",
        title=title,
        last_message_id=7,
        last_seen_at=datetime.now(UTC),
    )
    asyncio.run(client.app.state.backend.sources.upsert_discovered_chat(chat))


def test_lists_discovered_chats_filtered_by_connection(client, op) -> None:
    _seed(client, connection="bc-1", chat_id=7001, title="Ada")
    _seed(client, connection="bc-2", chat_id=42, title="Acme")

    everything = client.get("/telegram/chats", headers=op).json()
    assert {(c["business_connection_id"], c["chat_id"]) for c in everything} == {
        ("bc-1", 7001),
        ("bc-2", 42),
    }

    bc1 = client.get("/telegram/chats?connection=bc-1", headers=op).json()
    assert [c["title"] for c in bc1] == ["Ada"]
    assert bc1[0]["chat_id"] == 7001


def test_discovered_chats_requires_operator(client, user) -> None:
    assert client.get("/telegram/chats", headers=user).status_code == 403
