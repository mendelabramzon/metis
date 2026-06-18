"""ModelProvider adapters.

- ``StubProvider``: deterministic, never external — serves any tier/sensitivity, so
  restricted data and CI route here. Returns configured canned responses.
- ``AnthropicProvider``: the async Anthropic SDK with adaptive thinking + effort and
  schema-bound structured output. The client is injected, so tests use recorded
  responses and CI never makes a live call.
- ``OpenAICompatProvider``: OpenAI-style endpoints, incl. local vLLM/Ollama.

All return a protocol ``ModelResponse`` carrying a fully-populated ``ModelRun``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import JsonValue

from metis_core._util import now_utc
from metis_core.llm.errors import ModelRefusalError
from metis_core.llm.pricing import cost_usd
from metis_core.llm.routing_config import DEFAULT_TIER_MODELS, task_tier
from metis_protocol import (
    ModelRequest,
    ModelResponse,
    ModelRun,
    ModelRunId,
    ModelTier,
    Sensitivity,
    is_at_least,
    new_id,
)

_DEFAULT_EFFORT = "high"


def _run(
    request: ModelRequest,
    *,
    provider: str,
    model: str,
    started: datetime,
    finished: datetime,
    model_version: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost: float | None = None,
    cache_hit: bool | None = None,
) -> ModelRun:
    return ModelRun(
        id=new_id(ModelRunId),
        task_class=request.task_class,
        provider=provider,
        model=model,
        model_version=model_version,
        prompt_version=request.prompt_version,
        sensitivity=request.sensitivity,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=(finished - started).total_seconds() * 1000.0,
        cache_hit=cache_hit,
        started_at=started,
        finished_at=finished,
    )


class StubProvider:
    """A deterministic local provider for CI/local/restricted data."""

    def __init__(
        self,
        *,
        name: str = "stub-local",
        model: str = "local-stub",
        responses: Mapping[str, tuple[str, JsonValue | None]] | None = None,
    ) -> None:
        self._name = name
        self._model = model
        # task_class value -> (text, structured payload)
        self._responses = dict(responses or {})

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_external(self) -> bool:
        return False

    def supports(self, tier: ModelTier, sensitivity: Sensitivity) -> bool:
        return True  # a local stand-in serves every tier and sensitivity

    async def generate(self, request: ModelRequest) -> ModelResponse:
        started = now_utc()
        text, structured = self._responses.get(request.task_class.value, ("", None))
        run = _run(
            request,
            provider=self._name,
            model=self._model,
            started=started,
            finished=now_utc(),
            input_tokens=sum(len(m.content) for m in request.messages) // 4,
            output_tokens=len(text) // 4,
            cost=0.0,
            cache_hit=False,
        )
        return ModelResponse(text=text, model_run=run, structured=structured)


class AnthropicProvider:
    """The Anthropic SDK behind the protocol ``ModelProvider`` interface.

    ``client`` is an ``anthropic.AsyncAnthropic`` (typed ``Any`` so a recorded-response
    fake can be injected in tests).
    """

    def __init__(
        self,
        client: Any,
        *,
        name: str = "anthropic",
        tiers: tuple[ModelTier, ...] = (ModelTier.STANDARD, ModelTier.FRONTIER),
        tier_models: Mapping[ModelTier, str] | None = None,
        effort: str = _DEFAULT_EFFORT,
    ) -> None:
        self._client = client
        self._name = name
        self._tiers = frozenset(tiers)
        self._tier_models = dict(tier_models or DEFAULT_TIER_MODELS)
        self._effort = effort

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_external(self) -> bool:
        return True

    def supports(self, tier: ModelTier, sensitivity: Sensitivity) -> bool:
        # External provider: never for restricted data, and only its served tiers.
        return tier in self._tiers and not is_at_least(sensitivity, Sensitivity.RESTRICTED)

    def _model_for(self, request: ModelRequest) -> str:
        tier = task_tier(request.task_class)
        return self._tier_models.get(tier, self._tier_models[ModelTier.FRONTIER])

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = self._model_for(request)
        output_config: dict[str, Any] = {"effort": self._effort}
        if request.response_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.response_schema}
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens or 4096,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in request.messages
                if m.role != "system"
            ],
            "thinking": {"type": "adaptive"},
            "output_config": output_config,
        }
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        if system:
            params["system"] = system

        started = now_utc()
        message = await self._client.messages.create(**params)
        finished = now_utc()

        if getattr(message, "stop_reason", None) == "refusal":
            raise ModelRefusalError(f"{model} refused (task={request.task_class.value})")

        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        usage = message.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        structured: JsonValue | None = None
        if request.response_schema is not None and text:
            structured = json.loads(text)

        run = _run(
            request,
            provider=self._name,
            model=model,
            started=started,
            finished=finished,
            model_version=getattr(message, "model", model),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost=cost_usd(model, usage.input_tokens, usage.output_tokens),
            cache_hit=cache_read > 0,
        )
        return ModelResponse(text=text, model_run=run, structured=structured)


class OpenAICompatProvider:
    """OpenAI-compatible chat endpoints (OpenAI, vLLM, Ollama).

    Local endpoints set ``is_external=False`` so they may serve restricted data; the
    HTTP ``client`` (an ``httpx.AsyncClient``-like) is injected.
    """

    def __init__(
        self,
        client: Any,
        *,
        name: str,
        model: str,
        is_external: bool,
        tiers: tuple[ModelTier, ...] = (ModelTier.LOCAL,),
        base_url: str = "",
    ) -> None:
        self._client = client
        self._name = name
        self._model = model
        self._is_external = is_external
        self._tiers = frozenset(tiers)
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_external(self) -> bool:
        return self._is_external

    def supports(self, tier: ModelTier, sensitivity: Sensitivity) -> bool:
        if tier not in self._tiers:
            return False
        return self._is_external is False or not is_at_least(sensitivity, Sensitivity.RESTRICTED)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens or 4096,
        }
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": request.response_schema},
            }
        started = now_utc()
        response = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        finished = now_utc()
        data = response.json()

        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
        if choice.get("finish_reason") == "content_filter":
            raise ModelRefusalError(f"{self._model} refused (content filter)")
        usage = data.get("usage", {})
        structured: JsonValue | None = None
        if request.response_schema is not None and text:
            structured = json.loads(text)

        run = _run(
            request,
            provider=self._name,
            model=self._model,
            started=started,
            finished=finished,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
        return ModelResponse(text=text, model_run=run, structured=structured)
