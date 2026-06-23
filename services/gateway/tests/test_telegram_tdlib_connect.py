"""The per-user TDLib login endpoints, driven over a fake tdjson (no libtdjson, no live account).

Each test provisions a user, points the backend at a TelegramConnectManager whose client factory
returns a scriptable fake, and feeds the ``updateAuthorizationState`` updates TDLib would emit. The
suite covers the QR path and the phone → code → 2FA path, that only the database-encryption key is
ever stored (never the code/password), and the not-configured / no-active-login guards.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import pytest
from fastapi.testclient import TestClient

from metis_core.security.crypto import Cryptobox, generate_key
from metis_gateway.errors import ConflictError
from metis_gateway.routers.telegram import _drive
from metis_gateway.telegram_connect import TDLIB_CONNECTOR, TelegramConnectManager
from metis_ingestion.connectors import ConnectorError
from metis_ingestion.security.cred_store import EncryptedCredentialStore


class _FakeTdjson:
    """A scriptable tdjson: ``feed`` the updates TDLib would emit; records what the session sent."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self._queue: deque[dict[str, Any]] = deque()

    def feed(self, *updates: dict[str, Any]) -> None:
        self._queue.extend(updates)

    def send(self, request: Any) -> None:
        self.sent.append(dict(request))

    def receive(self, timeout: float = 1.0) -> dict[str, Any] | None:
        return self._queue.popleft() if self._queue else None

    def close(self) -> None:
        self.closed = True


def _auth(kind: str, **extra: Any) -> dict[str, Any]:
    return {"@type": "updateAuthorizationState", "authorization_state": {"@type": kind, **extra}}


def _install(client: TestClient, fake: _FakeTdjson) -> EncryptedCredentialStore:
    """Wire a connect manager (over ``fake``) onto the backend; return its credential store."""
    credentials = EncryptedCredentialStore(Cryptobox(generate_key()))
    client.app.state.backend.telegram_connect = TelegramConnectManager(
        client_factory=lambda: fake,
        credentials=credentials,
        api_id=42,
        api_hash="apihash",
        database_root="/tmp/metis-tdlib-test",
        poll_timeout=0.0,
    )
    return credentials


def _user(client: TestClient, op: dict[str, str]) -> tuple[str, dict[str, str]]:
    org_id = client.post("/organizations", json={"name": "Acme"}, headers=op).json()["id"]
    resp = client.post(
        "/users",
        json={"organization_id": org_id, "email": "ada@acme.example", "display_name": "Ada"},
        headers=op,
    )
    assert resp.status_code == 201, resp.text
    user_id: str = resp.json()["id"]
    return user_id, {"Authorization": f"Bearer {user_id}"}


def test_qr_login_surfaces_the_link_then_reaches_ready(
    client: TestClient, op: dict[str, str]
) -> None:
    user_id, ada = _user(client, op)
    fake = _FakeTdjson()
    credentials = _install(client, fake)

    fake.feed(
        _auth("authorizationStateWaitTdlibParameters"),
        _auth("authorizationStateWaitPhoneNumber"),
        _auth("authorizationStateWaitOtherDeviceConfirmation", link="tg://login?token=abc"),
    )
    started = client.post("/telegram/tdlib/connect", json={"use_qr": True}, headers=ada).json()
    assert started == {"state": "wait_qr", "qr_link": "tg://login?token=abc"}
    assert any(s["@type"] == "requestQrCodeAuthentication" for s in fake.sent)

    fake.feed(_auth("authorizationStateReady"))  # the user scanned the QR on their phone
    done = client.get("/telegram/tdlib/connect", headers=ada).json()
    assert done["state"] == "ready"
    assert fake.closed  # gateway releases its client so the worker can open the TDLib database

    # The database-encryption key is persisted (encrypted); status survives the login finishing.
    assert credentials.ciphertext(connector=TDLIB_CONNECTOR, name=f"db_key:{user_id}") is not None
    assert client.get("/telegram/tdlib/connect", headers=ada).json()["state"] == "ready"


def test_phone_code_then_two_factor_password(client: TestClient, op: dict[str, str]) -> None:
    user_id, ada = _user(client, op)
    fake = _FakeTdjson()
    credentials = _install(client, fake)

    fake.feed(
        _auth("authorizationStateWaitTdlibParameters"),
        _auth("authorizationStateWaitPhoneNumber"),
    )
    started = client.post(
        "/telegram/tdlib/connect", json={"phone": "+15550001234"}, headers=ada
    ).json()
    assert started["state"] == "wait_code"
    assert any(s["@type"] == "setAuthenticationPhoneNumber" for s in fake.sent)

    fake.feed(_auth("authorizationStateWaitPassword"))  # this account has 2FA enabled
    coded = client.post("/telegram/tdlib/connect/code", json={"code": "12345"}, headers=ada).json()
    assert coded["state"] == "wait_password"
    assert {"@type": "checkAuthenticationCode", "code": "12345"} in fake.sent

    fake.feed(_auth("authorizationStateReady"))
    final = client.post(
        "/telegram/tdlib/connect/password", json={"password": "hunter2"}, headers=ada
    ).json()
    assert final["state"] == "ready"
    assert {"@type": "checkAuthenticationPassword", "password": "hunter2"} in fake.sent

    # Only the db key is at rest — the login code and 2FA password were consumed, never stored.
    telegram_secrets = [
        n for n in credentials._store.names() if n.startswith(f"{TDLIB_CONNECTOR}:")
    ]
    assert telegram_secrets == [f"{TDLIB_CONNECTOR}:db_key:{user_id}"]


def test_connect_requires_configuration(client: TestClient, op: dict[str, str]) -> None:
    _user_id, ada = _user(client, op)  # telegram_connect left unset (the default)
    resp = client.post("/telegram/tdlib/connect", json={"use_qr": True}, headers=ada)
    assert resp.status_code == 409


def test_submit_without_an_active_login_is_404(client: TestClient, op: dict[str, str]) -> None:
    _user_id, ada = _user(client, op)
    _install(client, _FakeTdjson())
    resp = client.post("/telegram/tdlib/connect/code", json={"code": "1"}, headers=ada)
    assert resp.status_code == 404


def test_connect_requires_a_known_user(client: TestClient, op: dict[str, str]) -> None:
    _install(client, _FakeTdjson())
    assert client.post("/telegram/tdlib/connect", json={}, headers=op).status_code == 401


def test_connect_maps_missing_libtdjson_to_409(client: TestClient, op: dict[str, str]) -> None:
    # libtdjson is only present under the telegram compose profile; loading it (ctypes) raises
    # OSError when it isn't mounted. That must be a clear 409, not a bare 500 (#96).
    _user_id, ada = _user(client, op)

    def _no_libtdjson() -> Any:
        raise OSError("tdjson: cannot open shared object file: No such file or directory")

    client.app.state.backend.telegram_connect = TelegramConnectManager(
        client_factory=_no_libtdjson,
        credentials=EncryptedCredentialStore(Cryptobox(generate_key())),
        api_id=42,
        api_hash="apihash",
        database_root="/tmp/metis-tdlib-test",
        poll_timeout=0.0,
    )
    resp = client.post("/telegram/tdlib/connect", json={"use_qr": True}, headers=ada)
    assert resp.status_code == 409, resp.text
    assert "libtdjson" in resp.json()["error"]["message"]


async def test_drive_maps_tdlib_connector_error_to_409() -> None:
    # A TDLib runtime/auth failure (e.g. a bad api id/hash) surfaces as ConnectorError; the connect
    # endpoints turn it into a 409 carrying the reason, not an opaque 500 (#96).
    def _boom(*_args: object, **_kwargs: object) -> Any:
        raise ConnectorError("invalid api id/hash")

    with pytest.raises(ConflictError) as excinfo:
        await _drive(_boom)
    assert excinfo.value.status_code == 409
    assert "invalid api id/hash" in excinfo.value.message
