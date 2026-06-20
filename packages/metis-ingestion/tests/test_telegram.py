"""Telegram connector: per-message CHAT_MESSAGE rendering over recorded fixtures, no live creds.

Mirrors the Gmail unit test — discover a chat's messages, fetch one, and assert the markdown the
pipeline parses carries the sender, thread context, and attachment references. Private chats
floor at CONFIDENTIAL; a public channel keeps the source's own (lower) sensitivity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metis_ingestion import mime
from metis_ingestion.connectors import (
    ConnectorRegistry,
    RecordedTransport,
    TelegramConnector,
    TelegramSourceConfig,
)
from metis_protocol import ArtifactKind, Sensitivity, WorkspaceId


def _telegram(connectors_root: Path, workspace: WorkspaceId) -> TelegramConnector:
    connector = ConnectorRegistry.with_defaults().create(
        "telegram",
        workspace_id=workspace,
        transport=RecordedTransport(connectors_root / "telegram"),
    )
    assert isinstance(connector, TelegramConnector)
    return connector


async def test_discovers_the_chat_messages_in_order(connectors_root, workspace) -> None:
    refs = await _telegram(connectors_root, workspace).discover(None)
    assert [ref.locator for ref in refs] == ["7001:1040", "7001:1042", "7001:1045", "7001:1048"]
    # Cursors are monotonic, so a watermark resumes strictly after the last seen message.
    assert [ref.cursor for ref in refs] == sorted(ref.cursor for ref in refs if ref.cursor)


async def test_renders_sender_reply_and_media(connectors_root, workspace) -> None:
    connector = _telegram(connectors_root, workspace)
    reply = next(r for r in await connector.discover(None) if r.locator == "7001:1042")

    raw, _ = await connector.fetch_with_bytes(reply)
    assert raw.media_type == mime.MD
    assert raw.kind is ArtifactKind.CHAT_MESSAGE
    assert raw.policy.sensitivity is Sensitivity.CONFIDENTIAL  # a private DM floors here

    text = connector.normalize(raw).text
    assert "Ada Lovelace" in text  # sender
    assert "In reply to Grace Hopper" in text  # thread context
    assert "roadmap.pdf" in text  # attachment reference


async def test_marks_an_edited_message(connectors_root, workspace) -> None:
    connector = _telegram(connectors_root, workspace)
    edited = next(r for r in await connector.discover(None) if r.locator == "7001:1048")
    raw, _ = await connector.fetch_with_bytes(edited)
    assert "edited" in connector.normalize(raw).text


async def test_public_channel_keeps_the_source_sensitivity(tmp_path: Path, workspace) -> None:
    # A public channel post is not floored above the source's configured (lower) sensitivity.
    root = tmp_path / "telegram"
    (root / "content").mkdir(parents=True)
    (root / "messages.json").write_text(
        json.dumps([{"id": "ch:9", "content_key": "content/ch-9.json", "cursor": "000000000009"}])
    )
    (root / "content" / "ch-9.json").write_text(
        json.dumps(
            {
                "message_id": 9,
                "chat": {"id": -100, "type": "channel", "title": "Acme Public"},
                "date": 1717228800,
                "sender": {"name": "Acme"},
                "text": "Release 2.0 is out.",
            }
        )
    )
    connector = TelegramConnector(
        workspace_id=workspace,
        transport=RecordedTransport(root),
        sensitivity=Sensitivity.INTERNAL,
    )
    ref = (await connector.discover(None))[0]
    raw, _ = await connector.fetch_with_bytes(ref)
    assert raw.policy.sensitivity is Sensitivity.INTERNAL  # not floored up to CONFIDENTIAL


def test_registry_validates_a_telegram_source_config() -> None:
    registry = ConnectorRegistry.with_defaults()
    parsed = registry.validate_config(
        "telegram", {"chat_id": 7001, "business_connection_id": "bc-1"}
    )
    assert isinstance(parsed, TelegramSourceConfig)
    assert parsed.chat_id == 7001
    assert parsed.chat_type == "private"  # defaulted


def test_registry_rejects_a_telegram_source_without_a_chat() -> None:
    registry = ConnectorRegistry.with_defaults()
    with pytest.raises(ValidationError):
        registry.validate_config("telegram", {"business_connection_id": "bc"})  # no chat_id


def test_registry_config_is_none_for_a_connector_without_a_schema() -> None:
    assert ConnectorRegistry.with_defaults().validate_config("imap", {}) is None
