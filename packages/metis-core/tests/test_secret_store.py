"""PostgresSecretStore: a durable, encrypted-at-rest secret store shared across processes.

The load-bearing properties for deployment: a secret written by one process (the gateway) is
readable by another (the ingest worker) and survives a restart — both back onto the same
``connector_secrets`` table — and the table holds only ciphertext. Runs against the migrated
testcontainers Postgres; the store derives its own sync (psycopg2) URL from the async one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from metis_core.security import PostgresSecretStore, SecretNotFoundError
from metis_core.security.crypto import Cryptobox, generate_key

# A shared key so a second store instance (a stand-in for the other process) decrypts the first's
# writes — in deployment both processes are configured with the same METIS_*_CRED_STORE_KEY.
_KEY = generate_key()


@pytest.fixture
def stores(db_url: str) -> Iterator[Callable[..., PostgresSecretStore]]:
    """A factory for secret stores over the test Postgres, disposing each engine at teardown."""
    built: list[PostgresSecretStore] = []

    def make(key: str = _KEY) -> PostgresSecretStore:
        store = PostgresSecretStore(db_url, Cryptobox(key))
        built.append(store)
        return store

    yield make
    for store in built:
        store.dispose()


def test_set_and_resolve_roundtrip(stores: Callable[..., PostgresSecretStore]) -> None:
    store = stores()
    store.set("gmail:refresh_token", "tok-roundtrip")
    assert store.resolve("gmail:refresh_token") == "tok-roundtrip"


def test_set_overwrites(stores: Callable[..., PostgresSecretStore]) -> None:
    store = stores()
    store.set("gmail:overwrite", "old")
    store.set("gmail:overwrite", "new")
    assert store.resolve("gmail:overwrite") == "new"


def test_missing_secret_raises(stores: Callable[..., PostgresSecretStore]) -> None:
    with pytest.raises(SecretNotFoundError):
        stores().resolve("nothing:here")


def test_only_ciphertext_is_stored(stores: Callable[..., PostgresSecretStore]) -> None:
    store = stores()
    store.set("telegram_tdlib:db_key:u-rest", "super-secret-value")
    token = store.ciphertext("telegram_tdlib:db_key:u-rest")
    assert token is not None
    assert "super-secret-value" not in token  # encrypted at rest
    assert store.ciphertext("telegram_tdlib:db_key:absent") is None


def test_durable_and_shared_across_instances(stores: Callable[..., PostgresSecretStore]) -> None:
    """One instance writes (the gateway login), a separate instance reads (the worker backfill)."""
    stores().set("telegram_tdlib:db_key:u-shared", "dbkey-xyz")
    reader = stores()  # a fresh store + engine over the same table — the "other process"
    assert reader.resolve("telegram_tdlib:db_key:u-shared") == "dbkey-xyz"


def test_delete_and_names(stores: Callable[..., PostgresSecretStore]) -> None:
    store = stores()
    store.set("gdrive:names-a", "x")
    store.set("gdrive:names-b", "y")
    assert {"gdrive:names-a", "gdrive:names-b"} <= set(store.names())
    store.delete("gdrive:names-a")
    assert "gdrive:names-a" not in store.names()
