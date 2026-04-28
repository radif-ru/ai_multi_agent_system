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


# ---- map-reduce (см. _docs/memory.md §3.3) -----------------------------


def _msgs(n: int) -> list[dict]:
    return [{"role": "user", "content": f"m{i}"} for i in range(n)]


async def test_summarize_short_log_single_pass(llm, mocker):
    chat_mock = mocker.patch.object(llm, "chat", return_value="резюме")
    s = Summarizer(llm=llm, system_prompt="SYS", chunk_messages=30)
    out = await s.summarize(_msgs(5), model="m")
    assert out == "резюме"
    assert chat_mock.call_count == 1


async def test_summarize_long_log_map_reduce(llm, mocker):
    """65 сообщений при chunk_messages=30 → 3 map + 1 reduce = 4 вызова."""
    calls: list[str] = []

    async def fake_chat(messages, *, model, temperature):
        # Различаем map и reduce по тексту user-сообщения.
        user_msg = messages[1]["content"]
        if "Сведи следующие частичные" in user_msg:
            calls.append("reduce")
            return "ИТОГО"
        calls.append("map")
        return f"part{len(calls)}"

    mocker.patch.object(llm, "chat", side_effect=fake_chat)
    s = Summarizer(llm=llm, system_prompt="SYS", chunk_messages=30)
    out = await s.summarize(_msgs(65), model="m")
    assert out == "ИТОГО"
    assert calls.count("map") == 3
    assert calls.count("reduce") == 1
    assert calls == ["map", "map", "map", "reduce"]


async def test_summarize_map_failure_propagates(llm, mocker):
    n = 0

    async def fake_chat(messages, *, model, temperature):
        nonlocal n
        n += 1
        if n == 2:
            raise LLMUnavailable("batch 2 down")
        return "part"

    mocker.patch.object(llm, "chat", side_effect=fake_chat)
    s = Summarizer(llm=llm, system_prompt="SYS", chunk_messages=10)
    with pytest.raises(LLMUnavailable):
        await s.summarize(_msgs(35), model="m")
    # Должно упасть на втором map-батче, до reduce не дойти.
    assert n == 2


def test_summarize_invalid_chunk_messages(llm):
    with pytest.raises(ValueError):
        Summarizer(llm=llm, system_prompt="SYS", chunk_messages=0)
