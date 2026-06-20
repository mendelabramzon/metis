"""The opt-in TDLib personal-account session: authorization + a backfill/enumeration client.

This is the auth + transport-plumbing half of the TDLib path (the rendering half is
:mod:`telegram_tdlib_transport`). It is enabled per user, never the default, for the two things the
Business bot cannot do: backfilling a chat's history and reading followed channels the user does not
administer.

Two pieces, both over an injected :class:`TdjsonClient` (the native ``libtdjson`` is never imported
here — a thin ctypes wrapper is wired in deployment and faked in tests, exactly as the bot client
takes an injected HTTP client):

- :class:`TelegramSession` — the authorization state machine. It maps TDLib's
  ``updateAuthorizationState`` to the next request (QR or phone, then login code, then 2FA password)
  and tracks the resulting :class:`AuthState`. Login codes and the 2FA password are *consumed*
  (sent) and immediately cleared — never retained or persisted. The only durable secret is TDLib's
  database encryption key, which the caller stores via the encrypted credential store; "store only
  encrypted session keys, never login codes or 2FA secrets."

- :class:`TelegramTdlibClient` — request/response calls for history backfill (``getChatHistory``,
  paged) and chat/channel enumeration (``getChats`` + ``getChat``), correlated by TDLib's ``@extra``
  echo. A TDLib flood wait (error 429) surfaces as :class:`RateLimitError` with the retry hint, so
  the worker backs off and polls conservatively.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from metis_ingestion.connectors.base import ConnectorError, RateLimitError


class AuthState(StrEnum):
    """The simplified TDLib authorization lifecycle the session exposes."""

    WAIT_PARAMETERS = "wait_parameters"  # TDLib needs setTdlibParameters (sent automatically)
    WAIT_PHONE = "wait_phone"  # needs a phone number (or switch to QR)
    WAIT_QR = "wait_qr"  # a QR link was issued; awaiting scan on the phone
    WAIT_CODE = "wait_code"  # needs the login code delivered to the account
    WAIT_PASSWORD = "wait_password"  # needs the 2FA (cloud) password
    READY = "ready"  # authorized; the client can make calls
    CLOSED = "closed"  # logged out / revoked / session closed


@runtime_checkable
class TdjsonClient(Protocol):
    """The low-level tdjson transport: send a request, receive the next update/response.

    The deployment implementation wraps ``libtdjson`` (``td_send`` / ``td_receive``); tests supply a
    fake. Requests/responses are TDLib JSON objects; a response echoes the request's ``@extra``.
    """

    def send(self, request: Mapping[str, Any]) -> None: ...

    def receive(self, timeout: float = 1.0) -> dict[str, Any] | None: ...


@dataclass
class TdlibParameters:
    """The ``setTdlibParameters`` payload. ``database_encryption_key`` is the only durable session
    secret — generate it once and persist it *encrypted* (the credential store)."""

    api_id: int
    api_hash: str
    database_directory: str
    database_encryption_key: str
    use_test_dc: bool = False
    device_model: str = "Metis"
    application_version: str = "1.0"
    system_language_code: str = "en"

    def as_request(self) -> dict[str, Any]:
        return {
            "@type": "setTdlibParameters",
            "use_test_dc": self.use_test_dc,
            "database_directory": self.database_directory,
            "database_encryption_key": self.database_encryption_key,
            "api_id": self.api_id,
            "api_hash": self.api_hash,
            "system_language_code": self.system_language_code,
            "device_model": self.device_model,
            "application_version": self.application_version,
        }


@dataclass
class TelegramSession:
    """Drives the TDLib login flow over a :class:`TdjsonClient`, never persisting codes/secrets.

    Feed each incoming update to :meth:`handle`; when a credential is required, provide it
    (:meth:`provide_phone` / :meth:`provide_code` / :meth:`provide_password` or :attr:`use_qr`) and
    the next ``handle`` of the same state sends it. :attr:`state` reflects where the flow is.
    """

    client: TdjsonClient
    parameters: TdlibParameters
    use_qr: bool = False
    state: AuthState = AuthState.WAIT_PARAMETERS
    qr_link: str | None = None
    _phone: str | None = field(default=None, repr=False)
    _code: str | None = field(default=None, repr=False)
    _password: str | None = field(default=None, repr=False)

    @property
    def is_ready(self) -> bool:
        return self.state is AuthState.READY

    def provide_phone(self, phone: str) -> None:
        self._phone = phone

    def provide_code(self, code: str) -> None:
        self._code = code  # consumed on the next WAIT_CODE update, then cleared — never persisted

    def provide_password(self, password: str) -> None:
        self._password = password  # consumed on the next WAIT_PASSWORD update, then cleared

    def handle(self, update: Mapping[str, Any]) -> AuthState:
        """Process one update; on an authorization-state change, send the next request."""
        if update.get("@type") != "updateAuthorizationState":
            return self.state
        auth = update.get("authorization_state", {})
        kind = auth.get("@type") if isinstance(auth, Mapping) else None
        if kind == "authorizationStateWaitTdlibParameters":
            self.client.send(self.parameters.as_request())
            self.state = AuthState.WAIT_PARAMETERS
        elif kind == "authorizationStateWaitPhoneNumber":
            self._begin_login()
        elif kind == "authorizationStateWaitOtherDeviceConfirmation":
            self.qr_link = str(auth.get("link")) if isinstance(auth, Mapping) else None
            self.state = AuthState.WAIT_QR
        elif kind == "authorizationStateWaitCode":
            self._submit_code()
        elif kind == "authorizationStateWaitPassword":
            self._submit_password()
        elif kind == "authorizationStateReady":
            self.state = AuthState.READY
        elif kind in (
            "authorizationStateLoggingOut",
            "authorizationStateClosing",
            "authorizationStateClosed",
        ):
            self.state = AuthState.CLOSED
        return self.state

    def _begin_login(self) -> None:
        if self.use_qr:
            self.client.send({"@type": "requestQrCodeAuthentication", "other_user_ids": []})
            self.state = AuthState.WAIT_QR
        elif self._phone is not None:
            self.client.send({"@type": "setAuthenticationPhoneNumber", "phone_number": self._phone})
            self.state = AuthState.WAIT_CODE  # TDLib will next ask for the code
        else:
            self.state = AuthState.WAIT_PHONE  # awaiting a phone number from the operator

    def _submit_code(self) -> None:
        if self._code is not None:
            self.client.send({"@type": "checkAuthenticationCode", "code": self._code})
            self._code = None  # a login code is single-use — drop it immediately
            self.state = AuthState.WAIT_PARAMETERS  # awaiting the next state (ready or 2FA)
        else:
            self.state = AuthState.WAIT_CODE

    def _submit_password(self) -> None:
        if self._password is not None:
            self.client.send({"@type": "checkAuthenticationPassword", "password": self._password})
            self._password = None  # never retain the 2FA secret
            self.state = AuthState.WAIT_PARAMETERS  # awaiting ready
        else:
            self.state = AuthState.WAIT_PASSWORD


_RETRY_AFTER = re.compile(r"retry after (\d+)", re.IGNORECASE)


class TelegramTdlibClient:
    """Request/response TDLib calls for backfill + enumeration over a :class:`TdjsonClient`.

    Each call tags the request with a unique ``@extra`` and reads updates until the matching
    response arrives, so unrelated updates streaming in are skipped. A flood wait (error 429)
    becomes a :class:`RateLimitError` carrying the retry hint.
    """

    def __init__(
        self, client: TdjsonClient, *, poll_timeout: float = 1.0, max_polls: int = 1000
    ) -> None:
        self._client = client
        self._poll_timeout = poll_timeout
        self._max_polls = max_polls
        self._extra = itertools.count(1)

    def _call(self, request: Mapping[str, Any]) -> dict[str, Any]:
        extra = f"req-{next(self._extra)}"
        self._client.send({**request, "@extra": extra})
        for _ in range(self._max_polls):
            message = self._client.receive(self._poll_timeout)
            if message is None or message.get("@extra") != extra:
                continue  # an unrelated update (or a timeout) — keep waiting for ours
            if message.get("@type") == "error":
                self._raise(message)
            return message
        raise ConnectorError(f"no TDLib response to {request.get('@type')!r}")

    @staticmethod
    def _raise(error: Mapping[str, Any]) -> None:
        message = str(error.get("message", "TDLib error"))
        if error.get("code") == 429:
            match = _RETRY_AFTER.search(message)
            after = float(match.group(1)) if match else None
            raise RateLimitError(f"TDLib flood wait: {message}", retry_after_seconds=after)
        raise ConnectorError(f"TDLib error: {message}")

    def get_chat_history(
        self, chat_id: int, *, from_message_id: int = 0, limit: int = 50
    ) -> list[dict[str, Any]]:
        """One page of a chat's history, newest-first from ``from_message_id`` (0 = latest)."""
        response = self._call(
            {
                "@type": "getChatHistory",
                "chat_id": chat_id,
                "from_message_id": from_message_id,
                "offset": 0,
                "limit": limit,
                "only_local": False,
            }
        )
        return list(response.get("messages") or [])

    def backfill(
        self, chat_id: int, *, page_size: int = 50, max_pages: int = 20
    ) -> list[dict[str, Any]]:
        """Page back through a chat's history (conservatively bounded), oldest-first.

        Walks ``getChatHistory`` from the latest message backwards until a page is empty or the page
        budget is spent, then returns the accumulated messages in ascending id order for the
        transport's per-chat cursor.
        """
        collected: dict[int, dict[str, Any]] = {}
        from_message_id = 0
        for _ in range(max_pages):
            page = self.get_chat_history(chat_id, from_message_id=from_message_id, limit=page_size)
            if not page:
                break
            for message in page:
                collected[int(message["id"])] = message
            from_message_id = min(int(message["id"]) for message in page)
        return [collected[mid] for mid in sorted(collected)]

    def list_chats(self, *, limit: int = 100) -> list[int]:
        """The ids of the account's chats (the main list) — the candidates for source selection."""
        response = self._call(
            {"@type": "getChats", "chat_list": {"@type": "chatListMain"}, "limit": limit}
        )
        return [int(cid) for cid in (response.get("chat_ids") or [])]

    def get_chat(self, chat_id: int) -> dict[str, Any]:
        """A chat object (title + type) — enumeration shows these for selection."""
        return self._call({"@type": "getChat", "chat_id": chat_id})

    def get_user(self, user_id: int) -> dict[str, Any]:
        """A user object — to resolve a message sender's name for the transport's lookups."""
        return self._call({"@type": "getUser", "user_id": user_id})

    def resolve_lookups(
        self, messages: Sequence[Mapping[str, Any]]
    ) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
        """Fetch the users + chats referenced as senders in ``messages`` (the transport lookups)."""
        user_ids: set[int] = set()
        chat_ids: set[int] = set()
        for message in messages:
            sender = message.get("sender_id")
            if isinstance(sender, Mapping):
                if isinstance(sender.get("user_id"), int):
                    user_ids.add(int(sender["user_id"]))
                elif isinstance(sender.get("chat_id"), int):
                    chat_ids.add(int(sender["chat_id"]))
        users = {uid: self.get_user(uid) for uid in sorted(user_ids)}
        chats = {cid: self.get_chat(cid) for cid in sorted(chat_ids)}
        return users, chats
