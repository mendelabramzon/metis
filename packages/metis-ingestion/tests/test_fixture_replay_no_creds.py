"""Connectors run against recorded fixtures with no live credentials.

This is the property that makes connectors testable and CI-safe: the same connector code runs over
a ``RecordedTransport`` with no secret resolver, no network, no tokens. Auth config names the
secrets a live run needs — but holds none of their values, and resolving a missing one fails closed.
"""

import pytest

from metis_ingestion.connectors import (
    AuthError,
    AuthMethod,
    ConnectorError,
    ConnectorRegistry,
    InMemorySecretResolver,
    RecordedTransport,
)


async def test_every_connector_replays_without_credentials(connectors_root, workspace) -> None:
    registry = ConnectorRegistry.with_defaults()
    for name in registry.names():
        connector = registry.create(
            name, workspace_id=workspace, transport=RecordedTransport(connectors_root / name)
        )
        refs = await connector.discover(None)  # no auth, no network
        assert refs
        raw, _ = await connector.fetch_with_bytes(refs[0])
        assert connector.normalize(raw).text.strip()


def test_auth_declares_secret_names_but_holds_no_values() -> None:
    spec = ConnectorRegistry.with_defaults().get("slack")
    assert spec is not None
    assert spec.auth.method is AuthMethod.TOKEN
    assert spec.auth.secret_names  # names only — values live in the resolver

    resolved = spec.auth.resolve(InMemorySecretResolver({"api_token": "xoxb-secret"}))
    assert resolved == {"api_token": "xoxb-secret"}


def test_missing_secret_fails_closed() -> None:
    spec = ConnectorRegistry.with_defaults().get("gdrive")
    assert spec is not None
    with pytest.raises(AuthError):
        spec.auth.resolve(InMemorySecretResolver({}))


def test_unknown_recorded_response_is_an_error(connectors_root, workspace) -> None:
    transport = RecordedTransport(connectors_root / "slack")
    with pytest.raises(ConnectorError):
        transport.read("does-not-exist.json")
