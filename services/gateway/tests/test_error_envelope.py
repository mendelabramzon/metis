"""The catch-all exception handler: any unexpected error degrades to the standard envelope (#97).

An exception that escapes a router without becoming a typed ``ApiError`` or a validation error would
otherwise leak as Starlette's opaque plain-text 500. ``install_error_handlers`` adds a catch-all so
such failures are observable (traceback logged) and still carry the machine-readable
``{"error": {"code", "message"}}`` shape every other failure uses.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings


def _app_that_raises(settings: GatewaySettings) -> TestClient:
    """A gateway with one route that raises an unexpected exception, and a client that returns the
    handler's response. Starlette's ServerErrorMiddleware re-raises, so the client suppresses it.
    """
    app = create_app(settings)

    @app.get("/_boom")
    async def _boom() -> None:
        raise RuntimeError("kaboom: a secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_internal_error_envelope(
    settings: GatewaySettings, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level(logging.ERROR, logger="metis_gateway.errors"),
        _app_that_raises(settings) as client,
    ):
        resp = client.get("/_boom")

    assert resp.status_code == 500
    assert resp.json() == {
        "error": {"code": "internal_error", "message": "an unexpected error occurred"}
    }
    # The internal detail goes to the logs (with a traceback + the request method/path), never to
    # the client.
    assert "kaboom" not in resp.text
    assert any(record.exc_info for record in caplog.records)
    assert any("GET /_boom" in record.getMessage() for record in caplog.records)


def test_typed_and_validation_errors_are_unchanged(client: TestClient, op: dict[str, str]) -> None:
    # The catch-all does not swallow the more specific handlers: an UnauthorizedError still renders
    # its own 401 envelope, and a request-body validation error still renders the 422 one.
    missing_auth = client.post("/organizations", json={"name": "Acme"})
    assert missing_auth.status_code == 401
    assert missing_auth.json()["error"]["code"] == "unauthorized"

    bad_body = client.post("/organizations", json={}, headers=op)
    assert bad_body.status_code == 422
    assert bad_body.json()["error"]["code"] == "invalid_request"
