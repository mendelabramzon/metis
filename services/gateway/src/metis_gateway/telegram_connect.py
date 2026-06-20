"""Per-user TDLib login: drive a :class:`TelegramSession` across requests, store only the db key.

The opt-in TDLib path needs a personal-account login (QR, or phone → code → 2FA). That spans several
HTTP requests, so this manager keeps each user's live :class:`TelegramSession` (over a native tdjson
client) in process between calls, advances the authorization state machine, and surfaces what the
user must do next: scan a QR link, enter the login code, or enter the 2FA password.

The only durable secret is TDLib's database-encryption key. It is generated once per user and stored
*encrypted* in the credential store, so the worker can reopen the same authorized TDLib database to
backfill (the gateway closes its own client the moment login succeeds, because a TDLib database may
be opened by only one client at a time). Login codes and the 2FA password are never persisted — the
session consumes and clears them.

The native client is built by an injected factory, so the suite drives the whole flow over a fake
tdjson (scripted ``updateAuthorizationState`` updates) with no ``libtdjson`` and no live account.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from metis_ingestion.connectors import AuthState, TdjsonClient, TdlibParameters, TelegramSession
from metis_ingestion.security.cred_store import EncryptedCredentialStore

#: The credential-store namespace + key prefix for the per-user database-encryption key.
TDLIB_CONNECTOR = "telegram_tdlib"
_DB_KEY_PREFIX = "db_key:"

#: Auth states that are "settled" — TDLib will not advance them without fresh user input, so the
#: pump stops on an empty receive when in one (vs. the transient WAIT_PARAMETERS, where more is
#: coming and an empty receive is just TDLib still working).
_SETTLED = frozenset(
    {
        AuthState.WAIT_PHONE,
        AuthState.WAIT_QR,
        AuthState.WAIT_CODE,
        AuthState.WAIT_PASSWORD,
        AuthState.READY,
        AuthState.CLOSED,
    }
)

#: Builds a fresh tdjson client for one login (the native one in deployment, a fake in tests).
TdjsonClientFactory = Callable[[], TdjsonClient]


class NoActiveConnectError(LookupError):
    """No TDLib login is in progress for this user (start one before submitting a code/password)."""


@dataclass(frozen=True)
class ConnectStatus:
    """Where a user's login is: the auth state, plus the QR link to scan while in ``WAIT_QR``."""

    state: AuthState
    qr_link: str | None = None


class TelegramConnectManager:
    """Drives + tracks each user's TDLib login (one live session per user, keyed by user id)."""

    def __init__(
        self,
        *,
        client_factory: TdjsonClientFactory,
        credentials: EncryptedCredentialStore,
        api_id: int,
        api_hash: str,
        database_root: str,
        poll_timeout: float = 1.0,
        max_updates: int = 100,
        max_empty_polls: int = 2,
    ) -> None:
        self._factory = client_factory
        self._credentials = credentials
        self._api_id = api_id
        self._api_hash = api_hash
        self._database_root = database_root
        self._poll_timeout = poll_timeout
        self._max_updates = max_updates
        self._max_empty_polls = max_empty_polls
        self._sessions: dict[str, TelegramSession] = {}
        self._terminal: dict[str, AuthState] = {}  # last READY/CLOSED, so status survives finishing

    def start(
        self, user_id: str, *, use_qr: bool = True, phone: str | None = None
    ) -> ConnectStatus:
        """Begin (or restart) a login: QR by default, or phone if one is given."""
        self._terminal.pop(user_id, None)
        params = TdlibParameters(
            api_id=self._api_id,
            api_hash=self._api_hash,
            database_directory=str(Path(self._database_root) / user_id),
            database_encryption_key=self._db_key(user_id),
        )
        session = TelegramSession(
            client=self._factory(), parameters=params, use_qr=phone is None and use_qr
        )
        if phone is not None:
            session.provide_phone(phone)
        self._sessions[user_id] = session
        return self._advance(user_id, session)

    def submit_code(self, user_id: str, code: str) -> ConnectStatus:
        """Push the login code delivered to the account, then advance."""
        session = self._active(user_id)
        session.provide_code(code)
        session.resume()
        return self._advance(user_id, session)

    def submit_password(self, user_id: str, password: str) -> ConnectStatus:
        """Push the 2FA (cloud) password, then advance."""
        session = self._active(user_id)
        session.provide_password(password)
        session.resume()
        return self._advance(user_id, session)

    def status(self, user_id: str) -> ConnectStatus:
        """The current status — pumping a live session (e.g. to pick up a QR scan), else the last
        terminal state if the login already finished."""
        session = self._sessions.get(user_id)
        if session is not None:
            return self._advance(user_id, session)
        terminal = self._terminal.get(user_id)
        if terminal is not None:
            return ConnectStatus(state=terminal)
        raise NoActiveConnectError(user_id)

    def close_all(self) -> None:
        """Close every in-flight login's client (gateway shutdown)."""
        for user_id in list(self._sessions):
            self._close(self._sessions.pop(user_id))

    def _active(self, user_id: str) -> TelegramSession:
        session = self._sessions.get(user_id)
        if session is None:
            raise NoActiveConnectError(user_id)
        return session

    def _advance(self, user_id: str, session: TelegramSession) -> ConnectStatus:
        state = self._pump(session)
        if state in (AuthState.READY, AuthState.CLOSED):
            self._finish(user_id, session)
        link = session.qr_link if state is AuthState.WAIT_QR else None
        return ConnectStatus(state=state, qr_link=link)

    def _pump(self, session: TelegramSession) -> AuthState:
        """Feed TDLib updates into the session until it settles or has nothing more to say."""
        empty = 0
        for _ in range(self._max_updates):
            update = session.client.receive(self._poll_timeout)
            if update is None:
                empty += 1
                if session.state in _SETTLED or empty >= self._max_empty_polls:
                    break
                continue
            empty = 0
            session.handle(update)
            if session.state in (AuthState.READY, AuthState.CLOSED):
                break
        return session.state

    def _finish(self, user_id: str, session: TelegramSession) -> None:
        # On READY the authorized TDLib database is persisted on disk; release this client so the
        # worker can open the same database. Remember the terminal state so status() still answers.
        self._terminal[user_id] = session.state
        self._sessions.pop(user_id, None)
        self._close(session)

    @staticmethod
    def _close(session: TelegramSession) -> None:
        close = getattr(session.client, "close", None)
        if callable(close):
            close()

    def _db_key(self, user_id: str) -> str:
        """The user's TDLib db-encryption key — reused if stored, else generated and stored."""
        name = f"{_DB_KEY_PREFIX}{user_id}"
        if self._credentials.ciphertext(connector=TDLIB_CONNECTOR, name=name) is not None:
            return self._credentials.for_connector(TDLIB_CONNECTOR).resolve(name)
        key = secrets.token_urlsafe(32)
        self._credentials.set_credential(connector=TDLIB_CONNECTOR, name=name, value=key)
        return key
