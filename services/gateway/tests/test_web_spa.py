"""With ``METIS_GATEWAY_WEB_DIST`` set, the gateway serves the built React SPA at / (API intact).

Browser navigations (``Sec-Fetch-Mode: navigate``) resolve to the SPA shell — including app routes
that shadow an API path like ``/sources`` — while the SPA's own ``fetch()`` falls through to the
routers. The OAuth-callback redirect (``/oauth``) and the API docs stay server-handled.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.settings import GatewaySettings

_SHELL = "<!doctype html><title>Metis SPA</title><div id=root></div>"
_NAV = {"sec-fetch-mode": "navigate"}  # what a browser sends for a top-level navigation


@pytest.fixture
def spa_dir(tmp_path: Path) -> Path:
    """A minimal Vite-shaped build: an index shell, a hashed asset, and a root static file."""
    (tmp_path / "index.html").write_text(_SHELL, encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app-abc123.js").write_text("console.log('metis')", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return tmp_path


@pytest.fixture
def spa_client(spa_dir: Path) -> Iterator[TestClient]:
    settings = GatewaySettings(
        operator_token="op-token", user_token="user-token", web_dist=str(spa_dir)
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_root_serves_the_spa_shell(spa_client: TestClient) -> None:
    resp = spa_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Metis SPA" in resp.text


def test_navigation_to_app_route_serves_the_shell(spa_client: TestClient) -> None:
    # A deep link / reload of a client-side route the API does not own.
    resp = spa_client.get("/ask", headers=_NAV)
    assert resp.status_code == 200
    assert "Metis SPA" in resp.text


def test_navigation_to_api_shadowed_route_serves_the_shell(spa_client: TestClient) -> None:
    # /sources is both an app route and `GET /sources` (the API). A browser navigation must reach
    # the SPA, not the JSON list — this is the collision the navigation check resolves.
    resp = spa_client.get("/sources", headers=_NAV)
    assert resp.status_code == 200
    assert "Metis SPA" in resp.text


def test_api_fetch_to_shadowed_route_reaches_the_router(spa_client: TestClient) -> None:
    # The SPA's own fetch() (Sec-Fetch-Mode: cors, not a navigation) must hit the API, not shell.
    resp = spa_client.get("/sources", headers={"sec-fetch-mode": "cors"})
    assert "Metis SPA" not in resp.text
    assert resp.status_code != 200  # operator-gated; unauthenticated -> not a 200 HTML shell


def test_oauth_callback_is_not_hijacked(spa_client: TestClient) -> None:
    # Google redirects the browser (a navigation) to /oauth/callback; it must reach the handler.
    resp = spa_client.get("/oauth/callback", headers=_NAV)
    assert "Metis SPA" not in resp.text


def test_health_stays_json_under_the_spa(spa_client: TestClient) -> None:
    resp = spa_client.get("/health", headers=_NAV)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_hashed_assets_are_served(spa_client: TestClient) -> None:
    resp = spa_client.get("/assets/app-abc123.js")
    assert resp.status_code == 200
    assert "metis" in resp.text


def test_root_static_files_are_served(spa_client: TestClient) -> None:
    resp = spa_client.get("/favicon.svg")
    assert resp.status_code == 200
    assert "svg" in resp.text


def test_console_still_served_without_web_dist() -> None:
    # Default (web_dist unset) keeps the legacy single-file operator console at /.
    with TestClient(create_app(GatewaySettings(operator_token="op-token"))) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "context exoskeleton" in resp.text
