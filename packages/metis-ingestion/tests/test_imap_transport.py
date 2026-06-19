"""The live ``ImapTransport`` drives imaplib into a cached mailbox snapshot for the connector.

A fake imaplib client (canned SELECT / UID SEARCH / UID FETCH) stands in for a live server, so it
needs no credentials and no network — like the recorded transport replaying fixtures.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from metis_ingestion.connectors import (
    ConnectorError,
    ImapConfig,
    ImapConnector,
    ImapTransport,
)
from metis_protocol import WorkspaceId

_WS = WorkspaceId("ws_" + "1" * 32)


class _FakeImap:
    """A minimal imaplib stand-in over a ``uid -> raw RFC822`` map."""

    def __init__(self, messages: dict[str, bytes]) -> None:
        self._messages = messages
        self.logged_out = False

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        return ("OK", [str(len(self._messages)).encode()])

    def uid(self, command: str, *args: str) -> tuple[str, list[object]]:
        if command == "SEARCH":
            return ("OK", [b" ".join(uid.encode() for uid in self._messages)])
        if command == "FETCH":
            uid = args[0]
            raw = self._messages[uid]
            envelope = f"{uid} (UID {uid} RFC822 {{{len(raw)}}})".encode()
            return ("OK", [(envelope, raw), b")"])
        return ("OK", [None])

    def logout(self) -> tuple[str, list[bytes]]:
        self.logged_out = True
        return ("BYE", [b"see ya"])


def _config() -> ImapConfig:
    return ImapConfig(host="mail.example", username="ada", password="secret")


def test_lists_and_reads_messages_then_logs_out() -> None:
    messages = {
        "101": b"Subject: One\r\n\r\nbody one\r\n",
        "102": b"Subject: Two\r\n\r\nbody two\r\n",
    }
    fake = _FakeImap(messages)
    transport = ImapTransport(_config(), client_factory=lambda: fake)

    assert list(transport.list_keys()) == ["101.eml", "102.eml"]
    assert transport.read("101.eml") == messages["101"]
    assert fake.logged_out  # the snapshot loaded and the connection closed


def test_unknown_key_raises_connector_error() -> None:
    transport = ImapTransport(_config(), client_factory=lambda: _FakeImap({"1": b"x\r\n\r\n"}))
    with pytest.raises(ConnectorError):
        transport.read("999.eml")


def test_snapshot_is_loaded_once_and_cached() -> None:
    opened = 0

    def factory() -> _FakeImap:
        nonlocal opened
        opened += 1
        return _FakeImap({"1": b"Subject: x\r\n\r\nhi\r\n"})

    transport = ImapTransport(_config(), client_factory=factory)
    transport.list_keys()
    transport.read("1.eml")
    transport.list_keys()
    assert opened == 1  # connected once; later reads hit the cache


async def test_imap_connector_reconstructs_a_thread_over_the_live_transport() -> None:
    root = (
        b"Subject: Roadmap\r\nMessage-ID: <root@x>\r\nDate: Mon, 01 Jun 2026 10:00:00 +0000\r\n"
        b"From: ada@example.com\r\n\r\nKickoff.\r\n"
    )
    reply = (
        b"Subject: Re: Roadmap\r\nMessage-ID: <reply@x>\r\nIn-Reply-To: <root@x>\r\n"
        b"Date: Mon, 01 Jun 2026 11:00:00 +0000\r\nFrom: grace@example.com\r\n\r\nLooks good.\r\n"
    )
    factory: Callable[[], _FakeImap] = lambda: _FakeImap({"1": root, "2": reply})  # noqa: E731
    connector = ImapConnector(
        workspace_id=_WS, transport=ImapTransport(_config(), client_factory=factory)
    )

    refs = await connector.discover(None)
    assert len(refs) == 1  # root + reply collapse into one thread

    _, data = await connector.fetch_with_bytes(refs[0])
    rendered = data.decode()
    assert "Kickoff." in rendered
    assert "Looks good." in rendered
