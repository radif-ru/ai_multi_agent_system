"""Тесты `app.services.llm.OllamaClient`.

Покрытие — по `_docs/testing.md` §3.2.
Все сценарии работают на моках, без сетевых вызовов.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from ollama import ResponseError

from app.services.llm import (
    LLMBadResponse,
    LLMTimeout,
    LLMUnavailable,
    OllamaClient,
)


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(base_url="http://localhost:11434", timeout=10.0)


def _chat_resp(text: str) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=text))


async def test_chat_success(client, mocker):
    mocker.patch.object(client._client, "chat", return_value=_chat_resp("hello"))
    out = await client.chat([{"role": "user", "content": "hi"}], model="qwen3.5:4b")
    assert out == "hello"


async def test_embed_success(client, mocker):
    mocker.patch.object(
        client._client, "embeddings", return_value=SimpleNamespace(embedding=[0.1, 0.2, 0.3])
    )
    out = await client.embed("text", model="nomic-embed-text")
    assert out == [0.1, 0.2, 0.3]


async def test_chat_timeout_maps_to_llm_timeout(client, mocker):
    mocker.patch.object(
        client._client, "chat", side_effect=httpx.TimeoutException("slow")
    )
    with pytest.raises(LLMTimeout):
        await client.chat([{"role": "user", "content": "hi"}], model="m")


async def test_chat_connect_error_maps_to_unavailable(client, mocker):
    mocker.patch.object(
        client._client, "chat", side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(LLMUnavailable):
        await client.chat([{"role": "user", "content": "hi"}], model="m")


async def test_chat_http_404_maps_to_bad_response(client, mocker):
    mocker.patch.object(
        client._client, "chat", side_effect=ResponseError("model not found", 404)
    )
    with pytest.raises(LLMBadResponse):
        await client.chat([{"role": "user", "content": "hi"}], model="m")


async def test_chat_http_5xx_maps_to_bad_response(client, mocker):
    mocker.patch.object(
        client._client, "chat", side_effect=ResponseError("server error", 500)
    )
    with pytest.raises(LLMBadResponse):
        await client.chat([{"role": "user", "content": "hi"}], model="m")


async def test_chat_empty_response_maps_to_bad_response(client, mocker):
    mocker.patch.object(client._client, "chat", return_value=_chat_resp(""))
    with pytest.raises(LLMBadResponse):
        await client.chat([{"role": "user", "content": "hi"}], model="m")


async def test_embed_empty_response_maps_to_bad_response(client, mocker):
    mocker.patch.object(
        client._client, "embeddings", return_value=SimpleNamespace(embedding=[])
    )
    with pytest.raises(LLMBadResponse):
        await client.embed("text", model="m")


async def test_embed_connect_error_maps_to_unavailable(client, mocker):
    mocker.patch.object(
        client._client, "embeddings", side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(LLMUnavailable):
        await client.embed("text", model="m")


async def test_chat_logs_metrics(client, mocker, caplog):
    mocker.patch.object(client._client, "chat", return_value=_chat_resp("answer"))
    with caplog.at_level("INFO", logger="app.services.llm"):
        await client.chat([{"role": "user", "content": "hi"}], model="qwen3.5:4b")
    assert any(
        "kind=chat" in r.message and "model=qwen3.5:4b" in r.message and "status=ok" in r.message
        for r in caplog.records
    )


def test_estimate_tokens_string():
    assert OllamaClient.estimate_tokens("a" * 40) == 10


def test_estimate_tokens_messages():
    msgs = [{"role": "user", "content": "x" * 12}, {"role": "assistant", "content": "y" * 8}]
    assert OllamaClient.estimate_tokens(msgs) == 5


async def test_close_does_not_raise(client):
    await client.close()
