"""ModelCapability: the manifest is self-validating, so an under-specified model cannot be built —
the gate that keeps a model from being enabled without declaring what routing/budgets need."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metis_protocol import ModelCapability, ModelKind, ModelTier, PrivacyTier


def _chat(**overrides: object) -> ModelCapability:
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


def test_a_well_specified_chat_manifest_is_accepted() -> None:
    manifest = _chat(supports_tools=True, supports_json=True, json_reliability=0.9)
    assert manifest.provider == "hf-llama-70b"
    assert ModelTier.FRONTIER in manifest.tiers
    assert manifest.privacy_tier is PrivacyTier.LOCAL


def test_chat_manifest_without_tiers_is_rejected() -> None:
    with pytest.raises(ValidationError, match="tiers"):
        _chat(tiers=())


def test_embed_manifest_requires_an_embedding_dim() -> None:
    with pytest.raises(ValidationError, match="embedding_dim"):
        ModelCapability(
            provider="bge",
            model_id="bge-m3",
            kind=ModelKind.EMBED,
            base_url="http://tei:80",
            privacy_tier=PrivacyTier.LOCAL,
            context_window=8192,
            max_output_tokens=512,
        )


def test_context_window_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _chat(context_window=0)
