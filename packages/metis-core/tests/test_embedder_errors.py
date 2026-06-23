"""The HTTP embedders surface a clear EmbeddingError (not a bare KeyError/JSONDecodeError) when the
endpoint returns an error or a response without vectors — e.g. an un-pulled Ollama model 404s with
``{"error": "model ... not found"}``, which used to crash retrieval with ``KeyError: 'embeddings'``.
"""

from __future__ import annotations

from typing import Any

import pytest

from metis_core.memory_index import (
    EMBEDDING_DIM,
    EmbeddingError,
    OllamaEmbedder,
    OpenAICompatEmbedder,
)


class _Resp:
    def __init__(self, payload: Any, *, status_code: int = 200, json_raises: bool = False) -> None:
        self._payload = payload
        self.status_code = status_code
        self._json_raises = json_raises

    def json(self) -> Any:
        if self._json_raises:
            raise ValueError("body is not JSON")
        return self._payload


class _Client:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def post(self, url: str, json: dict[str, Any]) -> _Resp:
        return self._resp


def _ollama(resp: _Resp) -> OllamaEmbedder:
    return OllamaEmbedder(_Client(resp), base_url="http://host.docker.internal:11434")


def _openai(resp: _Resp) -> OpenAICompatEmbedder:
    return OpenAICompatEmbedder(
        _Client(resp),
        model="bge-m3",
        version="bge-m3@1",
        dim=EMBEDDING_DIM,
        base_url="http://tei/v1",
        is_external=False,
    )


async def test_ollama_model_not_found_surfaces_the_endpoint_message() -> None:
    resp = _Resp({"error": 'model "bge-m3" not found, try pulling it first'}, status_code=404)
    with pytest.raises(EmbeddingError, match="not found"):
        await _ollama(resp).embed(["hello"])


async def test_ollama_missing_embeddings_key_raises_embedding_error() -> None:
    with pytest.raises(EmbeddingError):
        await _ollama(_Resp({})).embed(["hello"])


async def test_ollama_non_json_body_raises_embedding_error() -> None:
    with pytest.raises(EmbeddingError):
        await _ollama(_Resp(None, json_raises=True)).embed(["hello"])


async def test_ollama_happy_path_returns_vectors() -> None:
    resp = _Resp({"embeddings": [[0.0] * EMBEDDING_DIM]})
    assert await _ollama(resp).embed(["hello"]) == [[0.0] * EMBEDDING_DIM]


async def test_openai_error_body_raises_embedding_error() -> None:
    with pytest.raises(EmbeddingError):
        await _openai(_Resp({"error": "bad request"}, status_code=400)).embed(["hello"])


async def test_openai_missing_data_raises_embedding_error() -> None:
    with pytest.raises(EmbeddingError):
        await _openai(_Resp({})).embed(["hello"])
