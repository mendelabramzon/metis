"""chat_provider_from_capability: a capability manifest maps onto a router provider with no
per-model adapter, so a self-hosted HF endpoint plugs straight into OpenAICompatProvider."""

from __future__ import annotations

from typing import Any

import pytest

from metis_core.llm import chat_provider_from_capability
from metis_protocol import (
    ModelCapability,
    ModelKind,
    ModelRequest,
    ModelTaskClass,
    ModelTier,
    PrivacyTier,
    Sensitivity,
)


class _FakeResponse:
    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


class _FakeHTTPClient:
    def __init__(self) -> None:
        self.url: str | None = None
        self.payload: dict[str, Any] | None = None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.url = url
        self.payload = json
        return _FakeResponse()


def _manifest(**overrides: object) -> ModelCapability:
    fields: dict[str, object] = {
        "provider": "hf-llama-70b",
        "model_id": "meta-llama/Llama-3.1-70B-Instruct",
        "kind": ModelKind.CHAT,
        "base_url": "http://gpu-box:8080/v1",
        "privacy_tier": PrivacyTier.LOCAL,
        "tiers": (ModelTier.STANDARD, ModelTier.FRONTIER),
        "context_window": 131072,
        "max_output_tokens": 4096,
    }
    fields.update(overrides)
    return ModelCapability(**fields)  # type: ignore[arg-type]


def _request() -> ModelRequest:
    return ModelRequest(
        task_class=ModelTaskClass.QUERY_ANSWER,
        messages=(),
        sensitivity=Sensitivity.INTERNAL,
    )


def test_local_manifest_serves_its_tiers_including_restricted_data() -> None:
    provider = chat_provider_from_capability(_manifest(), _FakeHTTPClient())
    assert provider.name == "hf-llama-70b"
    assert provider.is_external is False  # privacy_tier LOCAL stays on-prem
    assert provider.supports(ModelTier.STANDARD, Sensitivity.INTERNAL)
    assert provider.supports(ModelTier.FRONTIER, Sensitivity.RESTRICTED)  # local may see restricted
    assert not provider.supports(ModelTier.LOCAL, Sensitivity.INTERNAL)  # tier not declared


def test_external_manifest_is_held_to_the_allowlist() -> None:
    provider = chat_provider_from_capability(
        _manifest(privacy_tier=PrivacyTier.EXTERNAL), _FakeHTTPClient()
    )
    assert provider.is_external is True
    assert provider.supports(ModelTier.STANDARD, Sensitivity.INTERNAL)
    assert not provider.supports(ModelTier.STANDARD, Sensitivity.RESTRICTED)  # external blocked


async def test_generate_targets_the_manifest_endpoint_and_model() -> None:
    client = _FakeHTTPClient()
    provider = chat_provider_from_capability(_manifest(), client)
    await provider.generate(_request())
    assert client.url == "http://gpu-box:8080/v1/chat/completions"  # the manifest's base_url
    assert client.payload is not None
    assert client.payload["model"] == "meta-llama/Llama-3.1-70B-Instruct"


def test_embed_manifest_is_not_a_chat_provider() -> None:
    embed = ModelCapability(
        provider="bge",
        model_id="bge-m3",
        kind=ModelKind.EMBED,
        base_url="http://tei:80",
        privacy_tier=PrivacyTier.LOCAL,
        context_window=8192,
        max_output_tokens=512,
        embedding_dim=1024,
    )
    with pytest.raises(ValueError, match="not a chat provider"):
        chat_provider_from_capability(embed, _FakeHTTPClient())
