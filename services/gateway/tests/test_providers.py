"""Capability-manifest registration through the gateway: a self-hosted model declared by a
ModelCapability is enabled as a router provider and visible to operators on GET /providers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from metis_gateway.app import create_app
from metis_gateway.models import build_model_plane
from metis_gateway.settings import GatewaySettings
from metis_protocol import AuditEvent, ModelCapability, ModelKind, ModelTier, PrivacyTier

_OP = {"Authorization": "Bearer op-token"}
_USER = {"Authorization": "Bearer user-token"}


def _manifest() -> ModelCapability:
    return ModelCapability(
        provider="hf-llama-70b",
        model_id="meta-llama/Llama-3.1-70B-Instruct",
        kind=ModelKind.CHAT,
        base_url="http://gpu-box:8080/v1",
        privacy_tier=PrivacyTier.LOCAL,
        tiers=(ModelTier.STANDARD, ModelTier.FRONTIER),
        context_window=131072,
        max_output_tokens=4096,
        supports_tools=True,
        supports_json=True,
        json_reliability=0.9,
    )


def _settings() -> GatewaySettings:
    return GatewaySettings(
        operator_token="op-token",
        user_token="user-token",
        workspace_id="ws_" + "1" * 32,
        model_manifests=(_manifest(),),
    )


@pytest.fixture
def manifest_client() -> Iterator[TestClient]:
    with TestClient(create_app(_settings())) as client:
        yield client


class _Sink:
    async def emit(self, event: AuditEvent) -> None:  # pragma: no cover - unused here
        return None


async def test_manifest_is_registered_as_a_router_provider() -> None:
    plane = build_model_plane(_settings(), audit_sink=_Sink())
    try:
        assert any(p.name == "hf-llama-70b" for p in plane.providers)  # enabled by its manifest
        assert [m.provider for m in plane.manifests] == ["hf-llama-70b"]
    finally:
        for closer in plane.closers:  # close the shared manifest http client the plane opened
            await closer()


def test_operator_sees_the_registered_manifest(manifest_client: TestClient) -> None:
    resp = manifest_client.get("/providers", headers=_OP)
    assert resp.status_code == 200, resp.text
    [view] = resp.json()
    assert view["provider"] == "hf-llama-70b"
    assert view["privacy_tier"] == "local"
    assert view["tiers"] == ["standard", "frontier"]
    assert view["context_window"] == 131072
    assert view["supports_tools"] is True


def test_providers_listing_is_operator_only(manifest_client: TestClient) -> None:
    assert manifest_client.get("/providers", headers=_USER).status_code == 403
    assert manifest_client.get("/providers").status_code == 401
