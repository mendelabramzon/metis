"""The vision/OCR model path: providers build image blocks, the router routes vision past the tier
gate (keeping the external allowlist), and call_vision_text returns a transcription. No live model.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from metis_core.llm import (
    AnthropicProvider,
    MetisModelRouter,
    ModelCaller,
    NoEligibleProviderError,
    OpenAICompatProvider,
    StubProvider,
)
from metis_core.llm.ocr import model_transcriber
from metis_protocol import (
    AuditEvent,
    ImagePart,
    ModelMessage,
    ModelRequest,
    ModelTaskClass,
    Sensitivity,
    WorkspaceId,
)

_IMG = ImagePart(media_type="image/png", data=b"PNG-BYTES")
_WS = WorkspaceId("ws_" + "a" * 32)


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="transcribed")],
            stop_reason="end_turn",
            model="claude-opus-4-8",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
        )


class _FakeAnthropic:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


async def test_anthropic_sends_an_image_block() -> None:
    client = _FakeAnthropic()
    request = ModelRequest(
        task_class=ModelTaskClass.PARSE_ASSIST,
        messages=(ModelMessage(role="user", content="OCR this", images=(_IMG,)),),
        requires_vision=True,
    )
    await AnthropicProvider(client=client).generate(request)
    content = client.messages.calls[0]["messages"][0]["content"]
    assert isinstance(content, list)  # text + image blocks, not a plain string
    image = next(block for block in content if block["type"] == "image")
    assert image["source"]["type"] == "base64"
    assert image["source"]["media_type"] == "image/png"


async def test_anthropic_text_only_stays_a_string() -> None:
    client = _FakeAnthropic()
    await AnthropicProvider(client=client).generate(
        ModelRequest(
            task_class=ModelTaskClass.QUERY_ANSWER,
            messages=(ModelMessage(role="user", content="hi"),),
        )
    )
    assert client.messages.calls[0]["messages"][0]["content"] == "hi"  # unchanged for text-only


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHTTP:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.posted.append(json)
        return _FakeResponse(
            {"choices": [{"message": {"content": "transcribed"}, "finish_reason": "stop"}]}
        )


async def test_openai_sends_an_image_url_part() -> None:
    http = _FakeHTTP()
    provider = OpenAICompatProvider(
        http, name="vllm", model="qwen-vl", is_external=False, supports_vision=True
    )
    await provider.generate(
        ModelRequest(
            task_class=ModelTaskClass.PARSE_ASSIST,
            messages=(ModelMessage(role="user", content="OCR this", images=(_IMG,)),),
            requires_vision=True,
        )
    )
    content = http.posted[0]["messages"][0]["content"]
    assert isinstance(content, list)
    part = next(p for p in content if p["type"] == "image_url")
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


def test_vision_routes_past_the_local_tier_gate() -> None:
    # PARSE_ASSIST is LOCAL-tier (no cloud model serves it); requires_vision overrides that.
    cloud = AnthropicProvider(client=_FakeAnthropic())  # external, supports_vision=True
    local = StubProvider()  # supports_vision=False
    router = MetisModelRouter([cloud, local])
    request = ModelRequest(
        task_class=ModelTaskClass.PARSE_ASSIST, messages=(), requires_vision=True
    )
    assert router.route(request).name == "anthropic"


def test_restricted_vision_skips_external_and_falls_to_a_local_vlm() -> None:
    cloud = AnthropicProvider(client=_FakeAnthropic())  # external — blocked for restricted data
    blind_local = StubProvider(name="blind")  # local but not vision-capable
    with pytest.raises(NoEligibleProviderError):
        MetisModelRouter([cloud, blind_local]).route(
            ModelRequest(
                task_class=ModelTaskClass.PARSE_ASSIST,
                messages=(),
                sensitivity=Sensitivity.RESTRICTED,
                requires_vision=True,
            )
        )
    local_vlm = StubProvider(name="local-vlm", supports_vision=True)
    chosen = MetisModelRouter([cloud, local_vlm]).route(
        ModelRequest(
            task_class=ModelTaskClass.PARSE_ASSIST,
            messages=(),
            sensitivity=Sensitivity.RESTRICTED,
            requires_vision=True,
        )
    )
    assert chosen.name == "local-vlm"  # restricted OCR stays local


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


async def test_call_vision_text_transcribes_and_audits() -> None:
    sink = _RecordingSink()
    vlm = StubProvider(
        name="local-vlm", supports_vision=True, responses={"parse_assist": ("page text", None)}
    )
    caller = ModelCaller(MetisModelRouter([vlm]), sink)
    text = await caller.call_vision_text(
        task_class=ModelTaskClass.PARSE_ASSIST,
        workspace_id=_WS,
        user_content="Transcribe the text in this image.",
        images=(_IMG,),
    )
    assert text == "page text"
    assert sink.events  # the OCR call was audited like any model call


async def test_model_transcriber_degrades_to_empty_without_a_vision_model() -> None:
    # Only a non-vision local provider: call_vision_text raises NoEligibleProviderError -> "".
    caller = ModelCaller(MetisModelRouter([StubProvider()]), _RecordingSink())
    transcribe = model_transcriber(caller, _WS)
    assert await transcribe("image/png", b"bytes", Sensitivity.INTERNAL) == ""
