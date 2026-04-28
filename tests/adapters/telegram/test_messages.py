"""Тесты handler'а произвольного текста.

См. `_docs/commands.md` § «Произвольный текст», `_docs/testing.md` §3.11.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.handlers import messages as messages_module
from app.adapters.telegram.handlers.messages import (
    LLM_BAD_RESPONSE_REPLY,
    LLM_TIMEOUT_REPLY,
    LLM_UNAVAILABLE_REPLY,
    MAX_INPUT_LENGTH,
    NON_TEXT_REPLY,
    TELEGRAM_MAX_MESSAGE_LENGTH,
    TOO_LONG_INPUT_REPLY,
    build_text_handler,
)
from app.services.conversation import ConversationStore
from app.services.llm import LLMBadResponse, LLMTimeout, LLMUnavailable
from app.services.model_registry import UserSettingsRegistry


# ---------- Фейки и фабрики --------------------------------------------------


@dataclass
class _FakeSettings:
    history_summary_threshold: int = 100  # по умолчанию очень высоко
    history_max_messages: int = 1000


class _FakeSummarizer:
    def __init__(self, *, summary: str = "СУММАРИ", error: Exception | None = None):
        self.summary = summary
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def summarize(
        self, messages: Any, *, model: str, **_kw: Any
    ) -> str:
        self.calls.append({"messages": list(messages), "model": model})
        if self.error is not None:
            raise self.error
        return self.summary


class _FakeExecutor:
    """Не используется напрямую: handle_user_task мы патчим."""


def _make_handler(
    *,
    settings: _FakeSettings | None = None,
    user_settings: UserSettingsRegistry | None = None,
    conversations: ConversationStore | None = None,
    summarizer: _FakeSummarizer | None = None,
    executor: Any = None,
):
    return build_text_handler(
        settings=settings or _FakeSettings(),
        user_settings=user_settings
        or UserSettingsRegistry(default_model="qwen3.5:4b"),
        conversations=conversations or ConversationStore(max_messages=20),
        summarizer=summarizer or _FakeSummarizer(),
        executor=executor or _FakeExecutor(),
    )


def _make_message(
    *, text: str | None = "привет", user_id: int = 42, chat_id: int = 777
) -> tuple[MagicMock, AsyncMock]:
    msg = MagicMock(spec=["from_user", "chat", "answer", "text"])
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.text = text
    msg.answer = AsyncMock()
    return msg, msg.answer


@pytest.fixture
def patch_handle_user_task(monkeypatch: pytest.MonkeyPatch):
    """Подменить `handle_user_task` в модуле messages."""

    def _patch(reply: str = "финальный ответ", *, error: Exception | None = None):
        calls: list[dict[str, Any]] = []

        async def fake(text: str, **kwargs: Any) -> str:
            calls.append({"text": text, **kwargs})
            if error is not None:
                raise error
            return reply

        monkeypatch.setattr(messages_module, "handle_user_task", fake)
        return calls

    return _patch


# ---------- Тесты ------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path_calls_orchestrator_and_replies(
    patch_handle_user_task,
) -> None:
    calls = patch_handle_user_task("ответ")
    conversations = ConversationStore(max_messages=20)
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    user_settings.set_model(42, "llama3:8b")
    handler = _make_handler(
        conversations=conversations, user_settings=user_settings
    )
    msg, answer = _make_message(text="посчитай 2+2")

    await handler(msg)

    # handle_user_task получил текст, user_id, chat_id, model и conversations.
    assert len(calls) == 1
    call = calls[0]
    assert call["text"] == "посчитай 2+2"
    assert call["user_id"] == 42
    assert call["chat_id"] == 777
    assert call["model"] == "llama3:8b"
    assert call["conversations"] is conversations
    # История содержит вопрос и ответ.
    assert conversations.get_history(42) == [
        {"role": "user", "content": "посчитай 2+2"},
        {"role": "assistant", "content": "ответ"},
    ]
    # Ответ отправлен пользователю.
    answer.assert_awaited_once_with("ответ")


@pytest.mark.asyncio
async def test_too_long_input_skips_orchestrator(patch_handle_user_task) -> None:
    calls = patch_handle_user_task()
    handler = _make_handler()
    msg, answer = _make_message(text="x" * (MAX_INPUT_LENGTH + 1))

    await handler(msg)

    assert calls == []
    answer.assert_awaited_once_with(TOO_LONG_INPUT_REPLY)


@pytest.mark.asyncio
async def test_non_text_message_is_rejected(patch_handle_user_task) -> None:
    calls = patch_handle_user_task()
    handler = _make_handler()
    msg, answer = _make_message(text=None)

    await handler(msg)

    assert calls == []
    answer.assert_awaited_once_with(NON_TEXT_REPLY)


@pytest.mark.asyncio
async def test_llm_unavailable_replies_and_logs_error(
    patch_handle_user_task, caplog: pytest.LogCaptureFixture
) -> None:
    patch_handle_user_task(error=LLMUnavailable("connection refused"))
    handler = _make_handler()
    msg, answer = _make_message()

    with caplog.at_level(logging.ERROR, logger="app.adapters.telegram.handlers.messages"):
        await handler(msg)

    answer.assert_awaited_once_with(LLM_UNAVAILABLE_REPLY)
    assert any("LLM unavailable" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_llm_timeout_replies_with_timeout_message(
    patch_handle_user_task,
) -> None:
    patch_handle_user_task(error=LLMTimeout("slow"))
    handler = _make_handler()
    msg, answer = _make_message()

    await handler(msg)

    answer.assert_awaited_once_with(LLM_TIMEOUT_REPLY)


@pytest.mark.asyncio
async def test_llm_bad_response_replies_with_format_message(
    patch_handle_user_task,
) -> None:
    patch_handle_user_task(error=LLMBadResponse("not json"))
    handler = _make_handler()
    msg, answer = _make_message()

    await handler(msg)

    answer.assert_awaited_once_with(LLM_BAD_RESPONSE_REPLY)


@pytest.mark.asyncio
async def test_long_reply_is_split_into_chunks(patch_handle_user_task) -> None:
    long = "a" * (TELEGRAM_MAX_MESSAGE_LENGTH * 2 + 5)
    patch_handle_user_task(long)
    handler = _make_handler()
    msg, answer = _make_message()

    await handler(msg)

    assert answer.await_count == 3
    parts = [c.args[0] for c in answer.await_args_list]
    assert "".join(parts) == long
    assert all(len(p) <= TELEGRAM_MAX_MESSAGE_LENGTH for p in parts)


@pytest.mark.asyncio
async def test_in_session_summary_runs_when_threshold_reached(
    patch_handle_user_task,
) -> None:
    patch_handle_user_task("короткий ответ")
    settings = _FakeSettings(history_summary_threshold=2)
    summarizer = _FakeSummarizer(summary="резюме истории")
    conversations = ConversationStore(max_messages=20)
    handler = _make_handler(
        settings=settings, summarizer=summarizer, conversations=conversations
    )
    msg, _ = _make_message(text="ещё вопрос")

    await handler(msg)

    assert len(summarizer.calls) == 1
    history = conversations.get_history(42)
    # После replace_with_summary: один system (резюме) + 2 хвостовых сообщения.
    assert history[0]["role"] == "system"
    assert "резюме истории" in history[0]["content"]
    assert len(history) == 3


@pytest.mark.asyncio
async def test_in_session_summary_failure_does_not_break_reply(
    patch_handle_user_task, caplog: pytest.LogCaptureFixture
) -> None:
    patch_handle_user_task("ответ")
    settings = _FakeSettings(history_summary_threshold=2)
    summarizer = _FakeSummarizer(error=RuntimeError("llm down"))
    conversations = ConversationStore(max_messages=20)
    handler = _make_handler(
        settings=settings, summarizer=summarizer, conversations=conversations
    )
    msg, answer = _make_message()

    with caplog.at_level(logging.WARNING, logger="app.adapters.telegram.handlers.messages"):
        await handler(msg)

    answer.assert_awaited_once_with("ответ")
    assert any("summary failed" in r.message for r in caplog.records)
