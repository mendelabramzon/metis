"""A live IMAP ``Transport``: hydrate a mailbox snapshot over imaplib, then serve it from cache.

The connector spine (``base``) expects a synchronous ``Transport`` (``list_keys`` + ``read``) over a
fixed set of responses — exactly what ``RecordedTransport`` serves from fixtures. This is the live
sibling: on first access it logs in, ``UID SEARCH``es the mailbox, ``UID FETCH``es each message's
RFC822 bytes into an in-process cache keyed ``<uid>.eml``, then logs out. Caching makes the snapshot
deterministic and avoids re-fetching (``ImapConnector`` reads every key several times per cycle) and
keeps reads byte-identical, so cursor replay holds. UIDs (stable across the mailbox) key the cache.

The imaplib client is injected (``client_factory``), so the suite exercises the transport against a
fake with no live server; in production the default factory opens a real ``IMAP4_SSL`` connection.
Reads block (imaplib is synchronous), like the recorded transport — a connector wraps them in its
async ``discover``/``fetch``; offloading the blocking snapshot to a thread is a later refinement.
"""

from __future__ import annotations

import contextlib
import imaplib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from metis_ingestion.connectors.auth import AuthMethod, ConnectorAuth, SecretResolver
from metis_ingestion.connectors.base import AuthError, ConnectorError


@dataclass(frozen=True)
class ImapConfig:
    """Where and how to reach a mailbox; username/password are already-resolved secret values."""

    host: str
    username: str
    password: str
    port: int = 993
    mailbox: str = "INBOX"
    use_ssl: bool = True

    @classmethod
    def from_auth(
        cls,
        *,
        host: str,
        auth: ConnectorAuth,
        resolver: SecretResolver,
        mailbox: str = "INBOX",
        port: int = 993,
        use_ssl: bool = True,
    ) -> ImapConfig:
        """Build a config from a BASIC ``ConnectorAuth`` by resolving its username/password secrets.

        ``basic_auth`` declares the two secret *names* in (username, password) order; the values are
        fetched here through the resolver, so a credential never lives in the config.
        """
        if auth.method is not AuthMethod.BASIC or len(auth.secret_names) != 2:
            raise AuthError("IMAP requires BASIC auth with a username and password secret")
        username_name, password_name = auth.secret_names
        return cls(
            host=host,
            username=resolver.resolve(username_name),
            password=resolver.resolve(password_name),
            mailbox=mailbox,
            port=port,
            use_ssl=use_ssl,
        )


def _rfc822(fetched: Any) -> bytes | None:
    """Pull the RFC822 payload out of an imaplib ``UID FETCH`` response."""
    for part in fetched or []:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes | bytearray):
            return bytes(part[1])
    return None


class ImapTransport:
    """A live IMAP ``Transport`` — a mailbox snapshot, cached after the first access."""

    def __init__(
        self, config: ImapConfig, *, client_factory: Callable[[], Any] | None = None
    ) -> None:
        self._config = config
        self._client_factory = client_factory or self._connect
        self._cache: dict[str, bytes] | None = None

    def _connect(self) -> Any:
        host, port = self._config.host, self._config.port
        client = (
            imaplib.IMAP4_SSL(host, port) if self._config.use_ssl else imaplib.IMAP4(host, port)
        )
        client.login(self._config.username, self._config.password)
        return client

    def _load(self) -> dict[str, bytes]:
        if self._cache is not None:
            return self._cache
        client = self._client_factory()
        cache: dict[str, bytes] = {}
        try:
            client.select(self._config.mailbox, readonly=True)
            _, search = client.uid("SEARCH", "ALL")
            uids = search[0].split() if search and search[0] else []
            for uid in uids:
                uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                _, fetched = client.uid("FETCH", uid_str, "(RFC822)")
                raw = _rfc822(fetched)
                if raw is not None:
                    cache[f"{uid_str}.eml"] = raw
        finally:
            with contextlib.suppress(Exception):  # a logout failure must not mask the snapshot
                client.logout()
        self._cache = cache
        return cache

    def list_keys(self, prefix: str = "") -> Sequence[str]:
        keys = sorted(self._load())
        return [k for k in keys if k.startswith(prefix)] if prefix else keys

    def read(self, key: str) -> bytes:
        try:
            return self._load()[key]
        except KeyError as exc:
            raise ConnectorError(f"no IMAP message {key!r}") from exc
