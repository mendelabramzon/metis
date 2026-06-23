"""The opt-in TDLib session: authorization state machine + the backfill/enumeration client.

The auth flow runs over a fake tdjson (no native libtdjson, no live account): it drives QR/phone →
code → 2FA → ready, sending the right request at each step and never retaining the login code or 2FA
password. The client correlates request/response by TDLib's ``@extra`` echo, pages history, and
turns a flood wait into a retryable rate-limit error.
"""

from __future__ import annotations

import base64
from collections import deque
from typing import Any

import pytest

from metis_ingestion.connectors import (
    AuthState,
    TdlibParameters,
    TelegramSession,
    TelegramTdlibClient,
)
from metis_ingestion.connectors.base import ConnectorError, RateLimitError

_PARAMS = TdlibParameters(
    api_id=1,
    api_hash="hash",
    database_directory="/tmp/td",
    database_encryption_key="sekret-key",
)


def _auth(kind: str, **extra: Any) -> dict[str, Any]:
    return {"@type": "updateAuthorizationState", "authorization_state": {"@type": kind, **extra}}


class _SendFake:
    """Records sent requests; emits nothing (the test drives ``handle`` with crafted updates)."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, request: Any) -> None:
        self.sent.append(dict(request))

    def receive(self, timeout: float = 1.0) -> dict[str, Any] | None:
        return None


# --- authorization state machine ---------------------------------------------------------------


def test_phone_code_ready_flow() -> None:
    fake = _SendFake()
    session = TelegramSession(client=fake, parameters=_PARAMS)
    session.provide_phone("+15550001111")
    session.provide_code("12345")

    assert (
        session.handle(_auth("authorizationStateWaitTdlibParameters")) is AuthState.WAIT_PARAMETERS
    )
    assert fake.sent[-1]["@type"] == "setTdlibParameters"
    # sent base64-encoded (TDLib decodes the `bytes` field from base64)
    assert fake.sent[-1]["database_encryption_key"] == base64.b64encode(b"sekret-key").decode(
        "ascii"
    )

    assert session.handle(_auth("authorizationStateWaitPhoneNumber")) is AuthState.WAIT_CODE
    assert fake.sent[-1] == {
        "@type": "setAuthenticationPhoneNumber",
        "phone_number": "+15550001111",
    }

    session.handle(_auth("authorizationStateWaitCode"))
    assert fake.sent[-1] == {"@type": "checkAuthenticationCode", "code": "12345"}

    assert session.handle(_auth("authorizationStateReady")) is AuthState.READY
    assert session.is_ready


def test_qr_flow_issues_a_link() -> None:
    fake = _SendFake()
    session = TelegramSession(client=fake, parameters=_PARAMS, use_qr=True)
    session.handle(_auth("authorizationStateWaitTdlibParameters"))

    assert session.handle(_auth("authorizationStateWaitPhoneNumber")) is AuthState.WAIT_QR
    assert fake.sent[-1]["@type"] == "requestQrCodeAuthentication"

    state = session.handle(
        _auth("authorizationStateWaitOtherDeviceConfirmation", link="tg://login?token=abc")
    )
    assert state is AuthState.WAIT_QR
    assert session.qr_link == "tg://login?token=abc"
    assert session.handle(_auth("authorizationStateReady")) is AuthState.READY


def test_two_factor_password_is_submitted() -> None:
    fake = _SendFake()
    session = TelegramSession(client=fake, parameters=_PARAMS)
    session.provide_phone("+1")
    session.provide_password("hunter2")
    session.handle(_auth("authorizationStateWaitPhoneNumber"))
    session.handle(_auth("authorizationStateWaitPassword"))
    assert fake.sent[-1] == {"@type": "checkAuthenticationPassword", "password": "hunter2"}


def test_login_code_and_password_are_not_retained() -> None:
    session = TelegramSession(client=_SendFake(), parameters=_PARAMS)
    session.provide_code("999")
    session.provide_password("pw")
    session.handle(_auth("authorizationStateWaitCode"))
    session.handle(_auth("authorizationStateWaitPassword"))
    assert session._code is None  # single-use secrets are dropped the moment they're sent
    assert session._password is None


def test_waits_for_input_when_no_credential_is_provided() -> None:
    fake = _SendFake()
    session = TelegramSession(client=fake, parameters=_PARAMS)  # no phone, not QR
    assert session.handle(_auth("authorizationStateWaitPhoneNumber")) is AuthState.WAIT_PHONE
    assert fake.sent == []  # nothing sent until the operator provides a number (or chooses QR)


def test_revocation_closes_the_session() -> None:
    session = TelegramSession(client=_SendFake(), parameters=_PARAMS)
    assert session.handle(_auth("authorizationStateClosed")) is AuthState.CLOSED


def test_resume_submits_a_code_provided_after_the_wait_update() -> None:
    fake = _SendFake()
    session = TelegramSession(client=fake, parameters=_PARAMS)
    session.provide_phone("+1")
    session.handle(_auth("authorizationStateWaitPhoneNumber"))  # -> WAIT_CODE
    session.handle(_auth("authorizationStateWaitCode"))  # code not provided yet: nothing sent
    assert session.state is AuthState.WAIT_CODE
    assert not any(s["@type"] == "checkAuthenticationCode" for s in fake.sent)

    session.provide_code("54321")  # the operator types it after the prompt
    assert session.resume() is AuthState.WAIT_PARAMETERS  # now it is pushed
    assert fake.sent[-1] == {"@type": "checkAuthenticationCode", "code": "54321"}
    assert session._code is None  # still single-use


def test_resume_is_a_noop_outside_a_wait_state() -> None:
    fake = _SendFake()
    session = TelegramSession(client=fake, parameters=_PARAMS)
    assert session.resume() is AuthState.WAIT_PARAMETERS  # initial state, nothing to push
    assert fake.sent == []


class _PumpFake:
    """A fake tdjson that replays a scripted list of updates, then times out (None)."""

    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self._queue = deque(updates)
        self.sent: list[dict[str, Any]] = []

    def send(self, request: Any) -> None:
        self.sent.append(dict(request))

    def receive(self, timeout: float = 1.0) -> dict[str, Any] | None:
        return self._queue.popleft() if self._queue else None


def test_pump_drives_a_reopened_session_to_ready() -> None:
    # Reopening an already-authorized database: TDLib asks for parameters, then jumps to ready with
    # no phone/code — exactly what the worker backfill drain relies on.
    fake = _PumpFake(
        [_auth("authorizationStateWaitTdlibParameters"), _auth("authorizationStateReady")]
    )
    session = TelegramSession(client=fake, parameters=_PARAMS)
    assert session.pump(poll_timeout=0.0) is AuthState.READY
    assert fake.sent[0]["@type"] == "setTdlibParameters"


def test_pump_stops_at_a_wait_state_when_input_is_needed() -> None:
    fake = _PumpFake(
        [_auth("authorizationStateWaitTdlibParameters"), _auth("authorizationStateWaitPhoneNumber")]
    )
    session = TelegramSession(client=fake, parameters=_PARAMS)  # no phone, not QR
    assert session.pump(poll_timeout=0.0) is AuthState.WAIT_PHONE  # awaits the operator, not READY


# --- backfill / enumeration client -------------------------------------------------------------


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


def test_get_chat_history_returns_the_page() -> None:
    fake = _RpcFake([{"@type": "messages", "messages": [{"id": 1}, {"id": 2}], "__echo__": True}])
    client = TelegramTdlibClient(fake)
    assert [m["id"] for m in client.get_chat_history(7001)] == [1, 2]
    assert fake.sent[-1]["@type"] == "getChatHistory"
    assert fake.sent[-1]["chat_id"] == 7001


def test_call_skips_unrelated_updates() -> None:
    fake = _RpcFake(
        [
            {"@type": "updateNewMessage"},  # a broadcast update with no @extra — skipped
            {"@type": "messages", "messages": [{"id": 9}], "__echo__": True},
        ]
    )
    assert [m["id"] for m in TelegramTdlibClient(fake).get_chat_history(7001)] == [9]


def test_flood_wait_becomes_a_rate_limit_error() -> None:
    fake = _RpcFake(
        [
            {
                "@type": "error",
                "code": 429,
                "message": "Too Many Requests: retry after 12",
                "__echo__": True,
            }
        ]
    )
    with pytest.raises(RateLimitError) as caught:
        TelegramTdlibClient(fake).get_chat_history(7001)
    assert caught.value.retry_after_seconds == 12.0


def test_other_errors_raise_connector_error() -> None:
    fake = _RpcFake(
        [{"@type": "error", "code": 400, "message": "Chat not found", "__echo__": True}]
    )
    with pytest.raises(ConnectorError):
        TelegramTdlibClient(fake).get_chat(123)


def test_backfill_pages_until_empty_then_sorts_ascending() -> None:
    fake = _RpcFake(
        [
            {"@type": "messages", "messages": [{"id": 30}, {"id": 20}], "__echo__": True},
            {"@type": "messages", "messages": [{"id": 10}], "__echo__": True},
            {"@type": "messages", "messages": [], "__echo__": True},
        ]
    )
    client = TelegramTdlibClient(fake)
    assert [m["id"] for m in client.backfill(7001, page_size=2, max_pages=5)] == [10, 20, 30]
    assert sum(1 for s in fake.sent if s["@type"] == "getChatHistory") == 3


def test_list_chats_enumerates_ids() -> None:
    fake = _RpcFake([{"@type": "chats", "chat_ids": [7001, 9999], "__echo__": True}])
    assert TelegramTdlibClient(fake).list_chats() == [7001, 9999]


def test_resolve_lookups_fetches_referenced_senders() -> None:
    fake = _RpcFake(
        [
            {"@type": "user", "id": 2, "first_name": "Grace", "__echo__": True},
            {"@type": "chat", "id": 555, "title": "Group", "__echo__": True},
        ]
    )
    messages = [
        {"id": 1, "sender_id": {"@type": "messageSenderUser", "user_id": 2}},
        {"id": 2, "sender_id": {"@type": "messageSenderChat", "chat_id": 555}},
    ]
    users, chats = TelegramTdlibClient(fake).resolve_lookups(messages)
    assert users[2]["first_name"] == "Grace"
    assert chats[555]["title"] == "Group"
