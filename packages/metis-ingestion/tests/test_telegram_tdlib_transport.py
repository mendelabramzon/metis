"""The opt-in TDLib transport: a page of chat history becomes the same per-chat snapshot the bot
path produces, with no native libtdjson and no live account.

TDLib messages (sender-by-id, ``content.@type``, ``formattedText``) map to the canonical shape the
connector renders, so backfilled history ingests as CHAT_MESSAGE artifacts through the unchanged
connector — only this chat's messages, sorted by a per-chat cursor, with replies/forwards/edits and
attachment references preserved.
"""

from __future__ import annotations

from typing import Any

from metis_ingestion.connectors import (
    TelegramSourceConfig,
    TelegramTdlibConfig,
    TelegramTdlibTransport,
    build_tdlib_connector,
)
from metis_protocol import ArtifactKind, Sensitivity, WorkspaceId


def _msg(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "@type": "message",
        "id": 1048576,
        "chat_id": 7001,
        "sender_id": {"@type": "messageSenderUser", "user_id": 2},
        "date": 1717228800,
        "content": {"@type": "messageText", "text": {"@type": "formattedText", "text": "hi"}},
    }
    base.update(over)
    return base


def _text(body: str) -> dict[str, Any]:
    return {"@type": "messageText", "text": {"@type": "formattedText", "text": body}}


_USERS: dict[int, dict[str, Any]] = {
    2: {"id": 2, "first_name": "Grace", "last_name": "Hopper", "username": "grace"},
    3: {"id": 3, "first_name": "Ada", "last_name": "Lovelace"},
}
_CHATS: dict[int, dict[str, Any]] = {
    7001: {"id": 7001, "title": "Ada & Grace", "type": {"@type": "chatTypePrivate"}},
    9999: {
        "id": 9999,
        "title": "Broadcast",
        "type": {"@type": "chatTypeSupergroup", "is_channel": True},
    },
}

_MESSAGES: list[dict[str, Any]] = [
    _msg(id=1048576, content=_text("Here's the plan.")),
    _msg(id=2097152, edit_date=1717229000, content=_text("Edited: Monday.")),
    _msg(
        id=3145728,
        content={
            "@type": "messageDocument",
            "document": {
                "file_name": "deck.pdf",
                "mime_type": "application/pdf",
                "document": {"remote": {"id": "DOC1"}},
            },
            "caption": {"@type": "formattedText", "text": "the deck"},
        },
    ),
    _msg(
        id=4194304,
        reply_to={"@type": "messageReplyToMessage", "message_id": 1048576},
        content=_text("thanks!"),
    ),
    _msg(
        id=5242880,
        sender_id={"@type": "messageSenderUser", "user_id": 3},
        forward_info={"origin": {"@type": "messageForwardOriginHiddenUser", "sender_name": "Anon"}},
        content=_text("forwarded note"),
    ),
    _msg(id=6291456, chat_id=9999, content=_text("a different chat")),  # filtered out
]

_CONFIG = TelegramSourceConfig(
    chat_id=7001, chat_type="private"
)  # business_connection_id="" (TDLib)


def _connector(workspace: WorkspaceId):
    return build_tdlib_connector(
        workspace_id=workspace,
        config=_CONFIG,
        sensitivity=Sensitivity.CONFIDENTIAL,
        messages=_MESSAGES,
        users=_USERS,
        chats=_CHATS,
    )


async def test_backfills_only_this_chat_in_cursor_order(workspace: WorkspaceId) -> None:
    refs = await _connector(workspace).discover(None)
    # chat 9999 is filtered out; the rest sort by the zero-padded TDLib id (ascending).
    assert [r.locator for r in refs] == [
        "7001:1048576",
        "7001:2097152",
        "7001:3145728",
        "7001:4194304",
        "7001:5242880",
    ]


async def test_cursor_resumes_after_a_watermark(workspace: WorkspaceId) -> None:
    connector = _connector(workspace)
    first = (await connector.discover(None))[0]
    after = await connector.discover(first.cursor)
    assert first.locator not in [r.locator for r in after]  # already-seen history is not re-fetched


async def test_renders_tdlib_content(workspace: WorkspaceId) -> None:
    connector = _connector(workspace)
    refs = {r.locator: r for r in await connector.discover(None)}

    doc_raw, _ = await connector.fetch_with_bytes(refs["7001:3145728"])
    assert doc_raw.kind is ArtifactKind.CHAT_MESSAGE
    body = connector.normalize(doc_raw).text
    assert "deck.pdf" in body  # the attachment reference
    assert "Grace Hopper" in body  # sender resolved from the users lookup

    edit_body = connector.normalize(
        (await connector.fetch_with_bytes(refs["7001:2097152"]))[0]
    ).text
    assert "edited" in edit_body

    reply_body = connector.normalize(
        (await connector.fetch_with_bytes(refs["7001:4194304"]))[0]
    ).text
    assert "In reply to Grace Hopper: Here's the plan." in reply_body  # excerpt from the batch

    fwd_body = connector.normalize((await connector.fetch_with_bytes(refs["7001:5242880"]))[0]).text
    assert "Forwarded from Anon" in fwd_body


def test_transport_emits_the_canonical_listing_shape() -> None:
    transport = TelegramTdlibTransport(
        TelegramTdlibConfig(chat_id=7001, chat_type="private"),
        messages=_MESSAGES,
        users=_USERS,
        chats=_CHATS,
    )
    # the same messages.json + content/<chat>-<id>.json shape the bot transport produces
    assert "messages.json" in transport.list_keys()
    assert "content/7001-1048576.json" in transport.list_keys()
    assert b"Here's the plan." in transport.read("content/7001-1048576.json")


async def test_a_followed_channel_keeps_the_source_level(workspace: WorkspaceId) -> None:
    # A followed channel (public) keeps the source's own sensitivity, not the private-chat floor.
    connector = build_tdlib_connector(
        workspace_id=workspace,
        config=TelegramSourceConfig(chat_id=9999, chat_type="channel"),
        sensitivity=Sensitivity.INTERNAL,
        messages=_MESSAGES,
        users=_USERS,
        chats=_CHATS,
    )
    [ref] = await connector.discover(None)  # only chat 9999's single message
    raw, _ = await connector.fetch_with_bytes(ref)
    assert raw.policy.sensitivity is Sensitivity.INTERNAL
