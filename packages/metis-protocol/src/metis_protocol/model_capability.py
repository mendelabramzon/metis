"""The capability manifest a model must present before it can be enabled.

Routing and budgets are *capability-driven, not name-driven*: a model is enabled because its
manifest declares what it can do — context window, tool/JSON support and reliability, embedding
dimension, vision/OCR, cost, latency, privacy tier — never because its name looked familiar. For a
self-hosted Hugging Face model the manifest's ``base_url`` is the OpenAI-compatible URL of its
TGI/vLLM/TEI server, which the existing ``OpenAICompatProvider`` consumes directly (no per-model
adapter). Like :class:`WorkspaceModelPolicy`, a manifest is operational config, not an audited
artifact, so it is not registered in the schema snapshot set.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from metis_protocol.enums import ModelKind, ModelTier, PrivacyTier
from metis_protocol.versioning import VersionedModel


class ModelCapability(VersionedModel):
    """A deployed model's declared capabilities — the manifest required before it is routed to.

    ``provider`` is the name the router knows it by and ``model_id`` is the name its endpoint
    expects; ``base_url`` is the OpenAI-compatible chat/embeddings URL. A chat manifest must declare
    the ``tiers`` it serves; an embed manifest must declare its ``embedding_dim`` (the index is
    version-gated on it, so a change is a re-index, never a silent dimension mismatch).
    """

    provider: str
    model_id: str
    kind: ModelKind
    base_url: str
    privacy_tier: PrivacyTier
    tiers: tuple[ModelTier, ...] = ()
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    supports_tools: bool = False
    supports_json: bool = False
    # Declared reliability of structured output, 0..1; at or above the strict threshold the provider
    # constrains decoding to the schema's grammar, below it falls back to looser JSON-object mode.
    json_reliability: float = Field(default=0.0, ge=0.0, le=1.0)
    embedding_dim: int | None = Field(default=None, gt=0)
    supports_vision: bool = False
    supports_ocr: bool = False
    tokenizer: str | None = None
    cost_per_1k_input_usd: float = Field(default=0.0, ge=0.0)
    cost_per_1k_output_usd: float = Field(default=0.0, ge=0.0)
    expected_latency_ms: int | None = Field(default=None, gt=0)
    quantization: str | None = None
    hardware: str | None = None

    @model_validator(mode="after")
    def _check_kind_requirements(self) -> ModelCapability:
        """A manifest can't be constructed unless it declares what its kind needs — the gate that
        keeps an under-specified model from ever being enabled."""
        if self.kind is ModelKind.CHAT and not self.tiers:
            raise ValueError("a chat manifest must declare the tiers it serves")
        if self.kind is ModelKind.EMBED and self.embedding_dim is None:
            raise ValueError("an embed manifest must declare its embedding_dim")
        return self
