"""Model-layer interfaces and their request/response DTOs.

``generate`` is async I/O; ``route``/``supports`` are pure decisions (sync). The
router enforces provider allowlists before prompt construction (policy outside
prompts); that logic lives in implementations, not here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field, JsonValue

from metis_protocol.base import ProtocolModel
from metis_protocol.enums import ModelTier, Sensitivity
from metis_protocol.provenance import ModelRun
from metis_protocol.tasks import ModelTaskClass


class ImagePart(ProtocolModel):
    """An inline image accompanying a message — base64'd in JSON, for vision/OCR calls."""

    media_type: str  # e.g. "image/png", "image/jpeg"
    data: bytes


class ModelMessage(ProtocolModel):
    role: str
    content: str
    images: tuple[ImagePart, ...] = ()  # present only for vision/OCR; text-only callers leave empty


class ModelRequest(ProtocolModel):
    task_class: ModelTaskClass
    messages: tuple[ModelMessage, ...]
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0)
    response_schema: JsonValue | None = None  # JSON Schema for structured output
    prompt_version: str | None = None
    # Route to a vision-capable provider (superseding the task's quality tier); the external
    # allowlist still applies, so restricted data needs a local vision model or the call is refused.
    requires_vision: bool = False


class ModelResponse(ProtocolModel):
    text: str
    model_run: ModelRun
    structured: JsonValue | None = None


@runtime_checkable
class ModelProvider(Protocol):
    @property
    def name(self) -> str: ...

    def supports(self, tier: ModelTier, sensitivity: Sensitivity) -> bool: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...


@runtime_checkable
class ModelRouter(Protocol):
    def route(self, request: ModelRequest) -> ModelProvider: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...
