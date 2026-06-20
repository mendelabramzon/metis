"""Secret storage: values encrypted at rest, resolved by name — the connector ``SecretResolver``.

A value is encrypted with a :class:`~metis_core.security.crypto.Cryptobox` before storage, so a
leaked store dump exposes only ciphertext. :class:`EncryptedSecretStore` satisfies the Stage 11
``SecretResolver`` (``resolve(name) -> str``), so a connector can pull a credential without the
gateway or a model ever seeing it. A keyring/KMS backend slots behind the same :class:`SecretStore`
protocol; the deployment profile (Stage 15) picks one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from metis_core.db.engine import to_sync_url
from metis_core.models.secrets import ConnectorSecretRow
from metis_core.security.crypto import Cryptobox


class SecretNotFoundError(KeyError):
    """No secret is stored under the requested name."""


@runtime_checkable
class SecretStore(Protocol):
    def set(self, name: str, value: str) -> None: ...

    def resolve(self, name: str) -> str: ...

    def delete(self, name: str) -> None: ...

    def names(self) -> list[str]: ...

    def ciphertext(self, name: str) -> str | None: ...


class EncryptedSecretStore:
    """Secrets held as ciphertext; plaintext is produced only on :meth:`resolve`."""

    def __init__(self, crypto: Cryptobox) -> None:
        self._crypto = crypto
        self._ciphertext: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        self._ciphertext[name] = self._crypto.encrypt(value)

    def resolve(self, name: str) -> str:
        token = self._ciphertext.get(name)
        if token is None:
            raise SecretNotFoundError(name)
        return self._crypto.decrypt(token)

    def delete(self, name: str) -> None:
        self._ciphertext.pop(name, None)

    def names(self) -> list[str]:
        return sorted(self._ciphertext)

    def ciphertext(self, name: str) -> str | None:
        """The stored ciphertext (no decryption) — lets callers prove at-rest data is encrypted."""
        return self._ciphertext.get(name)


class PostgresSecretStore:
    """A durable, encrypted-at-rest :class:`SecretStore` over Postgres (sync), shared across procs.

    The deployment backend behind the connector secret store: a secret the gateway writes (an OAuth
    refresh token, a TDLib database-encryption key) is readable by the ingest worker and survives a
    restart, because both read/write the same ``connector_secrets`` table. Values are encrypted with
    the same :class:`Cryptobox` as the in-memory store, so a table dump reveals only ciphertext. It
    is sync — the ``SecretStore`` interface is sync, used deep in connector composition — over a
    small psycopg2 engine against the same Postgres the async stores use; secret ops are infrequent.
    """

    def __init__(self, database_url: str, crypto: Cryptobox) -> None:
        self._engine = create_engine(to_sync_url(database_url), pool_pre_ping=True, future=True)
        self._crypto = crypto

    def set(self, name: str, value: str) -> None:
        token = self._crypto.encrypt(value)
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            row = session.get(ConnectorSecretRow, name)
            if row is None:
                session.add(ConnectorSecretRow(name=name, ciphertext=token, updated_at=now))
            else:
                row.ciphertext = token
                row.updated_at = now

    def resolve(self, name: str) -> str:
        token = self.ciphertext(name)
        if token is None:
            raise SecretNotFoundError(name)
        return self._crypto.decrypt(token)

    def delete(self, name: str) -> None:
        with Session(self._engine) as session, session.begin():
            row = session.get(ConnectorSecretRow, name)
            if row is not None:
                session.delete(row)

    def names(self) -> list[str]:
        with Session(self._engine) as session:
            return sorted(session.scalars(select(ConnectorSecretRow.name)).all())

    def ciphertext(self, name: str) -> str | None:
        with Session(self._engine) as session:
            row = session.get(ConnectorSecretRow, name)
            return row.ciphertext if row is not None else None

    def dispose(self) -> None:
        """Close the engine's connection pool (call on service shutdown)."""
        self._engine.dispose()
