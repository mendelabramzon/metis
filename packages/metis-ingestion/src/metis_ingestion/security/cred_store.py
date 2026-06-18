"""Encrypted connector credentials: a ``SecretResolver`` backed by the core encrypted secret store.

Connector auth (Stage 11) *names* the secrets it needs; this resolves them from an at-rest-encrypted
store, namespaced per connector so two connectors' tokens never collide. Values are encrypted by the
core ``Cryptobox``, so a dumped store reveals only ciphertext. ``for_connector`` hands a connector a
``SecretResolver`` scoped to its own namespace — the Stage 11 interface, with encryption at rest.
"""

from __future__ import annotations

from metis_core.security import Cryptobox, EncryptedSecretStore


class ConnectorSecretResolver:
    """A ``SecretResolver`` scoped to one connector's namespace."""

    def __init__(self, store: EncryptedSecretStore, connector: str) -> None:
        self._store = store
        self._connector = connector

    def resolve(self, name: str) -> str:
        return self._store.resolve(f"{self._connector}:{name}")


class EncryptedCredentialStore:
    """Per-connector credentials, encrypted at rest with a core ``Cryptobox``."""

    def __init__(self, crypto: Cryptobox) -> None:
        self._store = EncryptedSecretStore(crypto)

    def set_credential(self, *, connector: str, name: str, value: str) -> None:
        self._store.set(f"{connector}:{name}", value)

    def for_connector(self, connector: str) -> ConnectorSecretResolver:
        return ConnectorSecretResolver(self._store, connector)

    def ciphertext(self, *, connector: str, name: str) -> str | None:
        """The stored ciphertext (no decryption) — proves credentials are encrypted at rest."""
        return self._store.ciphertext(f"{connector}:{name}")
