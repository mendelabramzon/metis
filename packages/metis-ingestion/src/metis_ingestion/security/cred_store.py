"""Encrypted connector credentials: a ``SecretResolver`` backed by the core encrypted secret store.

Connector auth (Stage 11) *names* the secrets it needs; this resolves them from an at-rest-encrypted
store, namespaced per connector so two connectors' tokens never collide. Values are encrypted by the
core ``Cryptobox``, so a dumped store reveals only ciphertext. ``for_connector`` hands a connector a
``SecretResolver`` scoped to its own namespace — the Stage 11 interface, with encryption at rest.
"""

from __future__ import annotations

from metis_core.security import Cryptobox, EncryptedSecretStore, SecretStore


class ConnectorSecretResolver:
    """A ``SecretResolver`` scoped to one connector's namespace."""

    def __init__(self, store: SecretStore, connector: str) -> None:
        self._store = store
        self._connector = connector

    def resolve(self, name: str) -> str:
        return self._store.resolve(f"{self._connector}:{name}")


class EncryptedCredentialStore:
    """Per-connector credentials, encrypted at rest, over an in-memory or durable ``SecretStore``.

    Pass a ``Cryptobox`` for the in-memory store (dev/tests), or a ``store`` (e.g. a
    ``PostgresSecretStore``) for the durable, cross-process backend used in deployment — the
    namespacing + connector resolver are identical either way.
    """

    def __init__(
        self, crypto: Cryptobox | None = None, *, store: SecretStore | None = None
    ) -> None:
        if store is not None:
            self._store: SecretStore = store
        elif crypto is not None:
            self._store = EncryptedSecretStore(crypto)
        else:
            raise ValueError("EncryptedCredentialStore needs a Cryptobox or a SecretStore")

    def set_credential(self, *, connector: str, name: str, value: str) -> None:
        self._store.set(f"{connector}:{name}", value)

    def for_connector(self, connector: str) -> ConnectorSecretResolver:
        return ConnectorSecretResolver(self._store, connector)

    def ciphertext(self, *, connector: str, name: str) -> str | None:
        """The stored ciphertext (no decryption) — proves credentials are encrypted at rest."""
        return self._store.ciphertext(f"{connector}:{name}")
