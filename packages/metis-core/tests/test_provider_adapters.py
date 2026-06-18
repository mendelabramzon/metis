"""AnthropicProvider against recorded/replayed responses (no live calls)."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from metis_core.llm import (
    AnthropicProvider,
    ModelError,
    ModelRefusalError,
    OpenAICompatProvider,
    schema_for,
)
from metis_protocol import (
    ExtractionBatch,
    ModelMessage,
    ModelRequest,
    ModelTaskClass,
    Sensitivity,
)
from metis_protocol.examples import extraction_batch


class _FakeMessages:
    def __init__(self, message: object) -> None:
        self._message = message
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self._message


class _FakeClient:
    def __init__(self, message: object) -> None:
        self.messages = _FakeMessages(message)


def _message(
    *,
    text: str,
    stop_reason: str = "end_turn",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model=model,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
        ),
    )


async def test_structured_request_shape_and_response() -> None:
    payload = json.dumps(extraction_batch().model_dump(mode="json"))
    client = _FakeClient(_message(text=payload))
    provider = AnthropicProvider(client=client)
    request = ModelRequest(
        task_class=ModelTaskClass.EXTRACT_CLAIMS,
        messages=(
            ModelMessage(role="system", content="sys"),
            ModelMessage(role="user", content="doc"),
        ),
        sensitivity=Sensitivity.INTERNAL,
        response_schema=schema_for(ExtractionBatch),
        max_tokens=2048,
    )
    response = await provider.generate(request)

    sent = client.messages.calls[0]
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"]["effort"]  # type: ignore[index]
    assert sent["output_config"]["format"]["type"] == "json_schema"  # type: ignore[index]
    assert sent["system"] == "sys"
    assert all(m["role"] != "system" for m in sent["messages"])  # type: ignore[attr-defined]
    assert sent["model"] == "claude-sonnet-4-6"  # STANDARD-tier task

    assert response.structured is not None
    assert response.model_run.input_tokens == 100
    assert response.model_run.output_tokens == 50
    assert response.model_run.cost_usd == pytest.approx(100 / 1e6 * 3 + 50 / 1e6 * 15)


async def test_refusal_raises() -> None:
    client = _FakeClient(_message(text="", stop_reason="refusal"))
    provider = AnthropicProvider(client=client)
    request = ModelRequest(
        task_class=ModelTaskClass.EXTRACT_CLAIMS,
        messages=(ModelMessage(role="user", content="x"),),
        sensitivity=Sensitivity.INTERNAL,
    )
    with pytest.raises(ModelRefusalError):
        await provider.generate(request)


async def test_frontier_task_uses_opus() -> None:
    client = _FakeClient(_message(text="hi", model="claude-opus-4-8"))
    provider = AnthropicProvider(client=client)
    request = ModelRequest(
        task_class=ModelTaskClass.QUERY_ANSWER,
        messages=(ModelMessage(role="user", content="x"),),
        sensitivity=Sensitivity.INTERNAL,
    )
    await provider.generate(request)
    assert client.messages.calls[0]["model"] == "claude-opus-4-8"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHTTPClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.posted: list[dict[str, Any]] = []

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.posted.append(json)
        return _FakeResponse(self._payload)


_OK_JSON = {
    "choices": [{"message": {"content": '{"x": 1}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 4},
}


def _openai_request() -> ModelRequest:
    return ModelRequest(
        task_class=ModelTaskClass.EXTRACT_CLAIMS,
        messages=(ModelMessage(role="user", content="doc"),),
        sensitivity=Sensitivity.INTERNAL,
        response_schema=schema_for(ExtractionBatch),
    )


async def test_openai_compat_error_body_raises_model_error() -> None:
    # A local runtime (e.g. Ollama) error object must surface cleanly, not as a KeyError.
    client = _FakeHTTPClient({"error": {"message": "failed to load model vocabulary"}})
    provider = OpenAICompatProvider(client, name="ollama", model="m", is_external=False)
    with pytest.raises(ModelError, match="failed to load model vocabulary"):
        await provider.generate(_openai_request())


async def test_openai_compat_non_json_content_does_not_crash() -> None:
    # Non-JSON content is left for the repair loop, not parsed eagerly into a crash.
    payload = {
        "choices": [{"message": {"content": "not json at all"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
    }
    provider = OpenAICompatProvider(
        _FakeHTTPClient(payload), name="ollama", model="m", is_external=False
    )
    response = await provider.generate(_openai_request())
    assert response.structured is None
    assert response.text == "not json at all"


async def test_local_provider_uses_json_object_mode_with_schema_in_prompt() -> None:
    # Local default: looser json_object mode (no grammar load), schema given in-prompt.
    client = _FakeHTTPClient(_OK_JSON)
    provider = OpenAICompatProvider(client, name="ollama", model="m", is_external=False)
    await provider.generate(_openai_request())
    sent = client.posted[0]
    assert sent["response_format"] == {"type": "json_object"}
    assert any("JSON Schema" in message["content"] for message in sent["messages"])


async def test_external_provider_uses_strict_json_schema_mode() -> None:
    # External default: precise grammar-constrained json_schema decoding, no prompt injection.
    client = _FakeHTTPClient(_OK_JSON)
    provider = OpenAICompatProvider(client, name="vllm", model="m", is_external=True)
    await provider.generate(_openai_request())
    sent = client.posted[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert all("JSON Schema" not in message["content"] for message in sent["messages"])
