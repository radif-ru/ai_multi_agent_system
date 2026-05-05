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
from app.core.events import EventBus, MessageReceived, ResponseGenerated
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
        or UserSettingsRegistry(
            default_model="qwen3.5:4b", default_search_engine="duckduckgo"
        ),
        conversations=conversations or ConversationStore(max_messages=20),
        summarizer=summarizer or _FakeSummarizer(),
        executor=executor or _FakeExecutor(),
    )


def _make_message(
    *, text: str | None = "привет", user_id: int = 42, chat_id: int = 777
) -> tuple[MagicMock, AsyncMock]:
    msg = MagicMock(spec=["from_user", "chat", "answer", "text", "bot"])
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.text = text
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.get_current_dispatcher.return_value.get.return_value = None
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


@pytest.fixture
def event_bus_with_conversations():
    """Создаёт EventBus с подписчиками для ConversationStore и мок для users."""
    event_bus = EventBus()
    conversations = ConversationStore(max_messages=20)
    from app.services.conversation_subscriber import on_message_received, on_response_generated
    from functools import partial
    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=conversations))

    # Мок для users
    from unittest.mock import AsyncMock, MagicMock
    mock_user = MagicMock()
    mock_user.external_id = "42"
    mock_users = MagicMock()
    mock_users.get_or_create = AsyncMock(return_value=(mock_user, False))

    return event_bus, conversations, mock_users


# ---------- Тесты ------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path_calls_orchestrator_and_replies(
    patch_handle_user_task,
    event_bus_with_conversations,
) -> None:
    calls = patch_handle_user_task("ответ")
    event_bus, conversations, mock_users = event_bus_with_conversations

    user_settings = UserSettingsRegistry(
        default_model="qwen3.5:4b", default_search_engine="duckduckgo"
    )
    user_settings.set_model(42, "llama3:8b")
    handler = _make_handler(
        conversations=conversations, user_settings=user_settings
    )
    msg, answer = _make_message(text="посчитай 2+2")
    # Добавляем event_bus и users в dispatcher
    msg.bot.get_current_dispatcher.return_value.get.side_effect = lambda key: {
        "users": mock_users,
        "event_bus": event_bus,
    }.get(key)

    await handler(msg)

    # handle_user_task получил текст, user_id, chat_id, model и conversations.
    assert len(calls) == 1
    call = calls[0]
    assert call["text"] == "посчитай 2+2"
    assert call["user_id"] == 42
    assert call["chat_id"] == 777
    assert call["model"] == "llama3:8b"
    assert call["conversations"] is conversations
    # История содержит вопрос и ответ (через подписчиков событий).
    assert conversations.get_history(42) == [
        {"role": "user", "content": "посчитай 2+2"},
        {"role": "assistant", "content": "ответ"},
    ]
    # Ответ отправлен пользователю.
    answer.assert_awaited_once_with("ответ", parse_mode=None)


@pytest.mark.asyncio
async def test_too_long_input_skips_orchestrator(patch_handle_user_task) -> None:
    calls = patch_handle_user_task()
    handler = _make_handler()
    msg, answer = _make_message(text="x" * (MAX_INPUT_LENGTH + 1))

    await handler(msg)

    assert calls == []
    answer.assert_awaited_once_with(TOO_LONG_INPUT_REPLY, parse_mode=None)


@pytest.mark.asyncio
async def test_non_text_message_is_rejected(patch_handle_user_task) -> None:
    calls = patch_handle_user_task()
    handler = _make_handler()
    msg, answer = _make_message(text=None)

    await handler(msg)

    assert calls == []
    answer.assert_awaited_once_with(NON_TEXT_REPLY, parse_mode=None)


@pytest.mark.asyncio
async def test_llm_unavailable_replies_and_logs_error(
    patch_handle_user_task, caplog: pytest.LogCaptureFixture
) -> None:
    patch_handle_user_task(error=LLMUnavailable("connection refused"))
    handler = _make_handler()
    msg, answer = _make_message()

    with caplog.at_level(logging.ERROR, logger="app.adapters.telegram.handlers.messages"):
        await handler(msg)

    answer.assert_awaited_once_with(LLM_UNAVAILABLE_REPLY, parse_mode=None)
    assert any("LLM недоступна" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_llm_timeout_replies_with_timeout_message(
    patch_handle_user_task,
) -> None:
    patch_handle_user_task(error=LLMTimeout("slow"))
    handler = _make_handler()
    msg, answer = _make_message()

    await handler(msg)

    answer.assert_awaited_once_with(LLM_TIMEOUT_REPLY, parse_mode=None)


@pytest.mark.asyncio
async def test_llm_bad_response_replies_with_format_message(
    patch_handle_user_task,
) -> None:
    patch_handle_user_task(error=LLMBadResponse("not json"))
    handler = _make_handler()
    msg, answer = _make_message()

    await handler(msg)

    expected_msg = "Модель ответила в неожиданном формате: not json. Попробуйте ещё раз."
    answer.assert_awaited_once_with(expected_msg, parse_mode=None)


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


# ---------- Reply-обработка -------------------------------------------------


@pytest.mark.asyncio
async def test_reply_to_text_message_includes_context(patch_handle_user_task, event_bus_with_conversations) -> None:
    """Reply на текстовое сообщение добавляет контекст оригинала."""
    patch_handle_user_task("ответ на reply")
    event_bus, conversations, mock_users = event_bus_with_conversations
    handler = _make_handler(conversations=conversations)
    msg, answer = _make_message(text="ответ пользователя")

    # Мокаем reply_to_message
    reply_msg = MagicMock()
    reply_msg.text = "оригинальное сообщение"
    reply_msg.message_id = 999
    msg.reply_to_message = reply_msg
    # Добавляем event_bus и users в dispatcher
    msg.bot.get_current_dispatcher.return_value.get.side_effect = lambda key: {
        "users": mock_users,
        "event_bus": event_bus,
    }.get(key)

    await handler(msg)

    # Проверяем, что ответ отправлен (контекст проверяется в интеграционных тестах)
    answer.assert_awaited_once_with("ответ на reply", parse_mode=None)


@pytest.mark.asyncio
async def test_reply_to_long_message_is_truncated(patch_handle_user_task, event_bus_with_conversations) -> None:
    """Reply на длинное сообщение обрезается до 500 символов."""
    patch_handle_user_task("ответ")
    event_bus, conversations, mock_users = event_bus_with_conversations
    handler = _make_handler(conversations=conversations)
    msg, answer = _make_message(text="ответ")

    reply_msg = MagicMock()
    reply_msg.text = "x" * 600
    reply_msg.message_id = 999
    msg.reply_to_message = reply_msg
    # Добавляем event_bus и users в dispatcher
    msg.bot.get_current_dispatcher.return_value.get.side_effect = lambda key: {
        "users": mock_users,
        "event_bus": event_bus,
    }.get(key)

    await handler(msg)

    # Проверяем, что ответ отправлен (обрезка контекста проверяется в интеграционных тестах)
    answer.assert_awaited_once_with("ответ", parse_mode=None)


@pytest.mark.asyncio
async def test_no_reply_without_reply_to_message(patch_handle_user_task, event_bus_with_conversations) -> None:
    """Обычное сообщение без reply не добавляет контекст."""
    patch_handle_user_task("ответ")
    event_bus, conversations, mock_users = event_bus_with_conversations
    handler = _make_handler(conversations=conversations)
    msg, answer = _make_message(text="просто текст")
    # Добавляем event_bus и users в dispatcher
    msg.bot.get_current_dispatcher.return_value.get.side_effect = lambda key: {
        "users": mock_users,
        "event_bus": event_bus,
    }.get(key)

    await handler(msg)

    history = conversations.get_history(42)
    assert len(history) == 2
    assert "[В ответ на:" not in history[0]["content"]
    answer.assert_awaited_once_with("ответ", parse_mode=None)

