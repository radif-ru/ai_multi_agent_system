"""Тесты `app.services.summarizer.Summarizer`."""

from __future__ import annotations

import pytest

from app.services.llm import LLMUnavailable, OllamaClient
from app.services.summarizer import Summarizer


@pytest.fixture
def llm() -> OllamaClient:
    return OllamaClient(base_url="http://localhost:11434", timeout=10.0)


async def test_summarize_calls_chat_with_system_prompt(llm, mocker):
    chat_mock = mocker.patch.object(llm, "chat", return_value="резюме")
    s = Summarizer(llm=llm, system_prompt="SYS")
    out = await s.summarize(
        [{"role": "user", "content": "a"}], model="qwen3.5:4b"
    )
    assert out == "резюме"
    args, kwargs = chat_mock.call_args
    payload = args[0]
    assert payload[0] == {"role": "system", "content": "SYS"}
    assert payload[1]["role"] == "user"
    assert "a" in payload[1]["content"]
    assert kwargs["model"] == "qwen3.5:4b"
    assert kwargs["temperature"] == 0.0


async def test_summarize_propagates_llm_error(llm, mocker):
    mocker.patch.object(llm, "chat", side_effect=LLMUnavailable("down"))
    s = Summarizer(llm=llm, system_prompt="SYS")
    with pytest.raises(LLMUnavailable):
        await s.summarize([{"role": "user", "content": "a"}], model="m")
