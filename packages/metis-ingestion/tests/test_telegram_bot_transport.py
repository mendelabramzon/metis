"""Live Telegram bot transport: convert Business-bot updates into a per-chat snapshot, no live API.

A batch of getUpdates results becomes the same messages.json + content shape the connector reads, so
only this source's connection + chat is ingested (others filtered out), an edit re-renders as new
content, and deletions are collected for tombstoning. ``TelegramBotClient.get_updates`` runs
against a fake HTTP client — no live Telegram.
"""

from __future__ import annotations

from typing import Any

import pytest

from metis_ingestion.connectors import (
    ConnectorError,
    TelegramBotClient,
    TelegramBotConfig,
    TelegramBotTransport,
    TelegramSourceConfig,
    build_telegram_connector,
)
from metis_protocol import ArtifactKind, Sensitivity, WorkspaceId


def _msg(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "message_id": 5,
        "business_connection_id": "bc-1",
        "chat": {"id": 7001, "type": "private", "first_name": "Ada", "last_name": "Lovelace"},
        "from": {"id": 2, "first_name": "Grace", "last_name": "Hopper", "username": "grace"},
        "date": 1717228800,
        "text": "hi",
    }
    base.update(over)
    return base


_UPDATES: list[dict[str, Any]] = [
    {
        "update_id": 1001,
        "business_message": _msg(
            message_id=5,
            text="Here's the deck.",
            document={"file_id": "DOC1", "file_name": "deck.pdf", "mime_type": "application/pdf"},
        ),
    },
    {
        "update_id": 1002,
        "edited_business_message": _msg(message_id=6, date=1717228900, text="Edited: Monday."),
    },
    {
        "update_id": 1003,
        "business_message": _msg(
            message_id=7, chat={"id": 9999, "type": "private"}, text="elsewhere"
        ),
    },
    {
        "update_id": 1004,
        "business_message": _msg(message_id=8, business_connection_id="bc-2", text="other conn"),
    },
    {
        "update_id": 1005,
        "deleted_business_messages": {
            "business_connection_id": "bc-1",
            "chat": {"id": 7001},
            "message_ids": [3, 4],
        },
    },
]

_CONFIG = TelegramSourceConfig(business_connection_id="bc-1", chat_id=7001)


def _connector(workspace: WorkspaceId, updates: list[dict[str, Any]] = _UPDATES):
    return build_telegram_connector(
        workspace_id=workspace,
        config=_CONFIG,
        sensitivity=Sensitivity.CONFIDENTIAL,
        updates=updates,
    )


async def test_ingests_only_this_connection_and_chat(workspace: WorkspaceId) -> None:
    refs = await _connector(workspace).discover(None)
    # only chat 7001 on connection bc-1: mid 5 (new) + mid 6 (edited); other chat/conn filtered.
    assert [r.locator for r in refs] == ["7001:5", "7001:6"]


async def test_renders_attachment_and_edit(workspace: WorkspaceId) -> None:
    connector = _connector(workspace)
    refs = {r.locator: r for r in await connector.discover(None)}

    doc_raw, _ = await connector.fetch_with_bytes(refs["7001:5"])
    assert doc_raw.kind is ArtifactKind.CHAT_MESSAGE
    assert "deck.pdf" in connector.normalize(doc_raw).text  # attachment reference

    edit_raw, _ = await connector.fetch_with_bytes(refs["7001:6"])
    assert "edited" in connector.normalize(edit_raw).text  # the edited marker


def test_collects_deletions_for_the_chat() -> None:
    transport = TelegramBotTransport(
        TelegramBotConfig(business_connection_id="bc-1", chat_id=7001), updates=_UPDATES
    )
    assert transport.deleted_message_ids == ("7001:3", "7001:4")


def test_an_edit_reuses_the_message_id_as_one_versioned_entry() -> None:
    # A new message and a later edit of the same id collapse to one listing entry; the edit's
    # content wins — a re-render is a new content-addressed artifact (a new version of the message).
    updates = [
        {"update_id": 1, "business_message": _msg(message_id=42, text="original")},
        {"update_id": 2, "edited_business_message": _msg(message_id=42, text="edited text")},
    ]
    transport = TelegramBotTransport(
        TelegramBotConfig(business_connection_id="bc-1", chat_id=7001), updates=updates
    )
    assert list(transport.list_keys()).count("content/7001-42.json") == 1
    body = transport.read("content/7001-42.json").decode()
    assert "edited text" in body
    assert '"edited": true' in body


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeBotHTTP:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.url: str | None = None
        self.params: dict[str, Any] = {}

    def get(self, url: str, params: dict[str, Any]) -> _Resp:
        self.url, self.params = url, params
        return _Resp(self.payload)


def test_get_updates_calls_the_bot_api() -> None:
    http = _FakeBotHTTP({"ok": True, "result": _UPDATES})
    client = TelegramBotClient(token="T0K", http_client=http, base_url="https://tg.example")

    result = client.get_updates(offset=1006)

    assert [u["update_id"] for u in result] == [1001, 1002, 1003, 1004, 1005]
    assert http.url == "https://tg.example/botT0K/getUpdates"
    assert http.params["offset"] == 1006
    assert "business_message" in http.params["allowed_updates"]


def test_get_updates_raises_on_api_error() -> None:
    http = _FakeBotHTTP({"ok": False, "description": "Unauthorized"})
    client = TelegramBotClient(token="bad", http_client=http)
    with pytest.raises(ConnectorError):
        client.get_updates()
