"""Build a router provider from a model's capability manifest.

A self-hosted Hugging Face model declares its OpenAI-compatible endpoint in its manifest, so it
plugs straight into :class:`OpenAICompatProvider` — capability-driven enablement with no per-model
adapter. The manifest's declared structured-output reliability selects the provider's JSON mode: a
reliable model uses strict schema-constrained decoding; a weak one uses the looser JSON-object mode
the caller's validate-and-repair loop still guarantees.
"""

from __future__ import annotations

from typing import Any

from metis_core.llm.provider import OpenAICompatProvider
from metis_protocol import ModelCapability, ModelKind, PrivacyTier

# At or above this declared reliability the provider constrains decoding to the schema's grammar;
# below it, the looser JSON-object mode (which the validate-and-repair loop still guarantees).
_STRICT_JSON_RELIABILITY = 0.8


def chat_provider_from_capability(capability: ModelCapability, client: Any) -> OpenAICompatProvider:
    """Map a CHAT manifest onto a router provider over ``client``; reject a non-chat manifest.

    ``privacy_tier`` becomes the provider's externality, so a ``LOCAL`` manifest may serve
    restricted data and an ``EXTERNAL`` one is held to the same allowlist as the cloud providers.
    """
    if capability.kind is not ModelKind.CHAT:
        raise ValueError(f"{capability.provider!r} is an embed manifest, not a chat provider")
    return OpenAICompatProvider(
        client,
        name=capability.provider,
        model=capability.model_id,
        is_external=capability.privacy_tier is PrivacyTier.EXTERNAL,
        tiers=capability.tiers,
        base_url=capability.base_url,
        json_object_mode=capability.json_reliability < _STRICT_JSON_RELIABILITY,
    )
