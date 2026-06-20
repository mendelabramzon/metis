"""EncryptedCredentialStore: per-connector namespacing over an in-memory or durable SecretStore.

The store adds the ``{connector}:{name}`` namespacing + the connector-scoped resolver; the backend
is pluggable — a Cryptobox (in-memory, dev/tests) or an injected SecretStore (e.g.
PostgresSecretStore in deployment). These check the namespacing, the resolver, encryption at rest,
and that an injected store is the one actually used.
"""

from __future__ import annotations

import pytest

from metis_core.security import EncryptedSecretStore
from metis_core.security.crypto import Cryptobox, generate_key
from metis_ingestion.security.cred_store import EncryptedCredentialStore


def test_namespaces_per_connector() -> None:
    creds = EncryptedCredentialStore(Cryptobox(generate_key()))
    creds.set_credential(connector="gmail", name="refresh_token", value="tok")
    assert creds.for_connector("gmail").resolve("refresh_token") == "tok"
    # the same name under a different connector is a different secret (no collision)
    assert creds.ciphertext(connector="gdrive", name="refresh_token") is None


def test_encrypted_at_rest() -> None:
    creds = EncryptedCredentialStore(Cryptobox(generate_key()))
    creds.set_credential(connector="telegram_tdlib", name="db_key:u-1", value="plain-key")
    token = creds.ciphertext(connector="telegram_tdlib", name="db_key:u-1")
    assert token is not None
    assert "plain-key" not in token


def test_injected_store_is_used() -> None:
    """Passing a SecretStore (the deployment path) routes reads/writes through it, namespaced."""
    backing = EncryptedSecretStore(Cryptobox(generate_key()))
    creds = EncryptedCredentialStore(store=backing)
    creds.set_credential(connector="gmail", name="refresh_token", value="tok")
    assert (
        backing.resolve("gmail:refresh_token") == "tok"
    )  # the wrapped store holds the namespaced key


def test_requires_a_crypto_or_a_store() -> None:
    with pytest.raises(ValueError, match="Cryptobox or a SecretStore"):
        EncryptedCredentialStore()
