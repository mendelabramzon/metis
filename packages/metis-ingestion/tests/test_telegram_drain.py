"""The Telegram drain pulls getUpdates once and fans the batch out to every active source, advancing
one global offset — so the per-chat sources don't steal each other's updates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from metis_ingestion import TelegramBotClient, drain_telegram_once
from metis_protocol import Sensitivity, SourceConfig, SourceId, WorkspaceId, new_id


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeBotHTTP:
    def __init__(self, result: list[dict[str, Any]]) -> None:
        self._result = result
        self.offsets: list[int] = []

    def get(self, url: str, params: dict[str, Any]) -> _Resp:
        self.offsets.append(params["offset"])
        return _Resp({"ok": True, "result": self._result})


def _source(name: str) -> SourceConfig:
    return SourceConfig(
        id=new_id(SourceId),
        workspace_id=new_id(WorkspaceId),
        name=name,
        connector="telegram",
        sensitivity=Sensitivity.CONFIDENTIAL,
        auth_method="token",
        created_at=datetime.now(UTC),
        config={"business_connection_id": "bc-1", "chat_id": 7001, "chat_type": "private"},
    )


_BATCH = [
    {
        "update_id": 10,
        "business_message": {
            "message_id": 1,
            "business_connection_id": "bc-1",
            "chat": {"id": 7001, "type": "private"},
            "date": 1,
            "text": "hi",
        },
    }
]


async def test_drains_once_and_fans_out_to_every_source() -> None:
    client = TelegramBotClient(token="T", http_client=_FakeBotHTTP(_BATCH))
    seen: list[tuple[str, int]] = []

    async def sync_source(source: SourceConfig, updates: Sequence[Mapping[str, Any]]) -> None:
        seen.append((source.name, len(updates)))

    next_offset = await drain_telegram_once(
        client=client, offset=0, sources=[_source("a"), _source("b")], sync_source=sync_source
    )

    assert [name for name, _ in seen] == ["a", "b"]  # the one drained batch reached both sources
    assert all(count == 1 for _, count in seen)
    assert next_offset == 11  # max update_id + 1, so the next call confirms this batch


async def test_empty_batch_keeps_the_offset_and_touches_nothing() -> None:
    client = TelegramBotClient(token="T", http_client=_FakeBotHTTP([]))
    touched = False

    async def sync_source(source: SourceConfig, updates: Sequence[Mapping[str, Any]]) -> None:
        nonlocal touched
        touched = True

    offset = await drain_telegram_once(
        client=client, offset=42, sources=[_source("a")], sync_source=sync_source
    )

    assert offset == 42  # nothing new -> the offset holds
    assert touched is False
