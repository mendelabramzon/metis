"""The native libtdjson binding's JSON marshalling, against a fake shared library.

Only :func:`load_tdjson_library` touches the real ``.so``; everything the client does — encode a
request to JSON bytes, decode a response, return None on a receive timeout, quiet logging on
construction, destroy the handle on close — is exercised here with no native library, exactly as the
session/transport run over a fake :class:`TdjsonClient`.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any

from metis_ingestion.connectors import NativeTdjsonClient
from metis_ingestion.connectors.telegram_session import TdjsonClient


class _FakeTdjson:
    """A stand-in ``libtdjson``: records sends/executes, replays a queue of received payloads."""

    def __init__(self, responses: list[bytes | None] | None = None) -> None:
        self.sent: list[bytes] = []
        self.executed: list[bytes] = []
        self.timeouts: list[float] = []
        self.destroyed = False
        self._responses: deque[bytes | None] = deque(responses or [])

    def td_json_client_create(self) -> Any:
        return object()  # an opaque handle, like the native c_void_p

    def td_json_client_send(self, client: Any, request: bytes) -> None:
        self.sent.append(request)

    def td_json_client_receive(self, client: Any, timeout: float) -> bytes | None:
        self.timeouts.append(timeout)
        return self._responses.popleft() if self._responses else None

    def td_json_client_execute(self, client: Any, request: bytes) -> bytes | None:
        self.executed.append(request)
        return b'{"@type": "ok"}'

    def td_json_client_destroy(self, client: Any) -> None:
        self.destroyed = True


def test_conforms_to_the_tdjson_client_protocol() -> None:
    assert isinstance(NativeTdjsonClient(_FakeTdjson()), TdjsonClient)


def test_send_encodes_the_request_as_json_bytes() -> None:
    fake = _FakeTdjson()
    NativeTdjsonClient(fake).send({"@type": "getChatHistory", "chat_id": 7001})
    assert json.loads(fake.sent[-1]) == {"@type": "getChatHistory", "chat_id": 7001}


def test_receive_decodes_a_json_response() -> None:
    fake = _FakeTdjson([b'{"@type": "messages", "total_count": 2}'])
    assert NativeTdjsonClient(fake).receive(2.5) == {"@type": "messages", "total_count": 2}
    assert fake.timeouts[-1] == 2.5  # the timeout is passed through to the native receive


def test_receive_returns_none_on_timeout() -> None:
    assert NativeTdjsonClient(_FakeTdjson()).receive() is None  # empty queue -> NULL pointer


def test_construction_quiets_logging_then_can_be_disabled() -> None:
    quiet = _FakeTdjson()
    NativeTdjsonClient(quiet, log_verbosity=0)
    assert json.loads(quiet.executed[-1]) == {
        "@type": "setLogVerbosityLevel",
        "new_verbosity_level": 0,
    }
    untouched = _FakeTdjson()
    NativeTdjsonClient(untouched, log_verbosity=None)
    assert untouched.executed == []  # None leaves TDLib's default verbosity alone


def test_close_destroys_the_handle() -> None:
    fake = _FakeTdjson()
    client = NativeTdjsonClient(fake)
    client.close()
    assert fake.destroyed
