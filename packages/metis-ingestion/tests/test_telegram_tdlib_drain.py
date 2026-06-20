"""The TDLib backfill drain: page each account's chats and ingest them like the bot path.

Everything runs over a fake tdjson (echoing TDLib's ``@extra``) and a fake account-session opener —
no ``libtdjson``, no live account. Covers ``backfill_chat`` assembling history + lookups, the drain
grouping sources by account and skipping an unauthorized one, and that the backfilled data renders
through ``build_tdlib_connector`` as discoverable CHAT_MESSAGE refs.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from metis_ingestion import drain_tdlib_once
from metis_ingestion.connectors import TelegramTdlibClient, build_tdlib_connector
from metis_ingestion.connectors.telegram import TelegramSourceConfig
from metis_ingestion.telegram_tdlib_drain import group_by_account
from metis_protocol import Sensitivity, SourceConfig, SourceId, WorkspaceId, new_id


class _RpcFake:
    """A fake tdjson: queued items marked ``__echo__`` receive the matching send's ``@extra``."""

    def __init__(self, queue: list[dict[str, Any]]) -> None:
        self._queue = deque(queue)
        self._extra: deque[Any] = deque()
        self.sent: list[dict[str, Any]] = []

    def send(self, request: Any) -> None:
        self.sent.append(dict(request))
        self._extra.append(request.get("@extra"))

    def receive(self, timeout: float = 1.0) -> dict[str, Any] | None:
        if not self._queue:
            return None
        item = dict(self._queue.popleft())
        if item.pop("__echo__", False):
            item["@extra"] = self._extra.popleft() if self._extra else None
        return item


def _message(message_id: int, *, chat_id: int, user_id: int, text: str) -> dict[str, Any]:
    return {
        "id": message_id,
        "chat_id": chat_id,
        "date": message_id * 10,
        "sender_id": {"@type": "messageSenderUser", "user_id": user_id},
        "content": {"@type": "messageText", "text": {"text": text}},
    }


def _backfill_fake() -> _RpcFake:
    """A fake serving one chat (7001): two messages from users 2 and 3, then the lookups."""
    return _RpcFake(
        [
            {  # getChatHistory page 1 (newest first)
                "@type": "messages",
                "messages": [
                    _message(20, chat_id=7001, user_id=3, text="world"),
                    _message(10, chat_id=7001, user_id=2, text="hello"),
                ],
                "__echo__": True,
            },
            {"@type": "messages", "messages": [], "__echo__": True},  # page 2 empty -> stop
            {"@type": "user", "id": 2, "first_name": "Ada", "__echo__": True},
            {"@type": "user", "id": 3, "first_name": "Bob", "__echo__": True},
            {  # the chat's own object (the transport's descriptor)
                "@type": "chat",
                "id": 7001,
                "title": "Ada & Bob",
                "type": {"@type": "chatTypeBasicGroup"},
                "__echo__": True,
            },
        ]
    )


async def test_backfill_chat_returns_history_with_lookups_and_renders() -> None:
    client = TelegramTdlibClient(_backfill_fake())
    messages, users, chats = client.backfill_chat(7001, page_size=2, max_pages=5)

    assert [m["id"] for m in messages] == [10, 20]  # ascending, for the per-chat cursor
    assert users[2]["first_name"] == "Ada"
    assert users[3]["first_name"] == "Bob"
    assert chats[7001]["title"] == "Ada & Bob"  # the chat's own descriptor was fetched

    # The backfilled shape feeds straight into the connector and discovers as CHAT_MESSAGE refs.
    connector = build_tdlib_connector(
        workspace_id=new_id(WorkspaceId),
        config=TelegramSourceConfig(chat_id=7001, chat_type="group", tdlib_user_id="u-1"),
        sensitivity=Sensitivity.CONFIDENTIAL,
        messages=messages,
        users=users,
        chats=chats,
    )
    refs = await connector.discover(None)
    assert [ref.locator for ref in refs] == ["7001:10", "7001:20"]


def _source(name: str, config: dict[str, Any]) -> SourceConfig:
    return SourceConfig(
        id=new_id(SourceId),
        workspace_id=new_id(WorkspaceId),
        name=name,
        connector="telegram",
        sensitivity=Sensitivity.CONFIDENTIAL,
        auth_method="token",
        created_at=datetime.now(UTC),
        config=config,
    )


def test_group_by_account_only_picks_active_tdlib_sources() -> None:
    tdlib = _source("tdlib", {"chat_id": 7001, "tdlib_user_id": "u-1"})
    bot = _source("bot", {"business_connection_id": "bc-1", "chat_id": 9003})
    inactive = _source("old", {"chat_id": 8002, "tdlib_user_id": "u-1"})
    inactive = inactive.model_copy(update={"active": False})

    groups = group_by_account([tdlib, bot, inactive])
    assert groups == {"u-1": [tdlib]}  # bot (no account) + inactive both excluded


async def test_drain_backfills_each_account_and_skips_unauthorized() -> None:
    authorized = _source("ada-group", {"chat_id": 7001, "tdlib_user_id": "u-1"})
    revoked = _source("bob-dm", {"chat_id": 8002, "tdlib_user_id": "u-2"})
    clients = {"u-1": TelegramTdlibClient(_backfill_fake()), "u-2": None}

    @contextmanager
    def account_sessions(user_id: str) -> Iterator[TelegramTdlibClient | None]:
        yield clients[user_id]  # "u-2" -> None: its session is not authorized

    synced: list[tuple[str, list[int]]] = []

    async def sync_source(
        source: SourceConfig,
        messages: Sequence[Mapping[str, Any]],
        _users: Mapping[int, Mapping[str, Any]],
        _chats: Mapping[int, Mapping[str, Any]],
    ) -> None:
        synced.append((source.name, [int(m["id"]) for m in messages]))

    count = await drain_tdlib_once(
        sources=[authorized, revoked],
        account_sessions=account_sessions,
        sync_source=sync_source,
        page_size=2,
        max_pages=5,
    )

    assert count == 1  # only the authorized account synced
    assert synced == [("ada-group", [10, 20])]  # the unauthorized account was skipped
