"""Тесты `app.services.summarizer_subscriber`."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.config import Settings
from app.core.events import ResponseGenerated
from app.services.conversation import ConversationStore
from app.services.model_registry import UserSettingsRegistry
from app.services.summarizer import Summarizer
from app.services.summarizer_subscriber import on_response_generated_summarize
from app.users.models import User


@pytest.fixture
def user() -> User:
    return User(
        id=1,
        channel="telegram",
        external_id="12345",
        display_name="Test User",
        created_at=datetime.now(),
    )


@pytest.fixture
def conversations() -> ConversationStore:
    return ConversationStore(
        max_messages=100,
        session_log_max_messages=50,
    )


@pytest.fixture
def summarizer(mocker):
    summarizer = Summarizer(llm=mocker.Mock(), system_prompt="test")
    return summarizer


@pytest.fixture
def user_settings() -> UserSettingsRegistry:
    return UserSettingsRegistry(default_model="qwen3.5:4b", default_search_engine="google")


@pytest.fixture
def settings() -> Settings:
    return Settings(history_summary_threshold=10)


async def test_summarize_when_history_exceeds_threshold(
    user, conversations, summarizer, user_settings, settings, mocker
):
    """При history_len >= threshold вызывается Summarizer.summarize и replace_with_summary."""
    # Заполняем историю до threshold (threshold = 10, добавляем 10 пар = 20 сообщений)
    # Используем int как user_id, потому что подписчик конвертирует external_id в int
    for i in range(10):
        conversations.add_user_message(12345, f"message {i}")
        conversations.add_assistant_message(12345, f"response {i}")

    # Добавляем ответ ассистента (имитация conversation_subscriber)
    conversations.add_assistant_message(12345, "new response")

    # Проверяем длину истории перед вызовом подписчика
    history_len = len(conversations.get_history(12345))
    print(f"History length before subscriber: {history_len}, threshold: {settings.history_summary_threshold}")

    # Мокаем summarize напрямую
    summarize_mock = mocker.patch.object(
        summarizer, "summarize", new_callable=mocker.AsyncMock, return_value="summary"
    )
    replace_mock = mocker.patch.object(
        conversations, "replace_with_summary"
    )

    event = ResponseGenerated(
        user=user,
        text="new response",
        conversation_id="12345",
        channel="telegram",
    )

    await on_response_generated_summarize(
        event,
        conversations=conversations,
        summarizer=summarizer,
        user_settings=user_settings,
        settings=settings,
    )

    # Проверяем, что summarize был вызван
    summarize_mock.assert_called_once()
    # Проверяем, что replace_with_summary был вызван
    replace_mock.assert_called_once_with(12345, "summary", kept_tail=2)


async def test_summarize_not_called_when_history_below_threshold(
    user, conversations, summarizer, user_settings, settings, mocker
):
    """При history_len < threshold суммаризация не вызывается."""
    # Заполняем историю ниже threshold
    for i in range(5):
        conversations.add_user_message("12345", f"message {i}")
        conversations.add_assistant_message("12345", f"response {i}")

    # Мокаем summarize
    summarize_mock = mocker.patch.object(
        summarizer, "summarize", return_value="summary"
    )
    replace_mock = mocker.patch.object(
        conversations, "replace_with_summary"
    )

    event = ResponseGenerated(
        user=user,
        text="new response",
        conversation_id="12345",
        channel="telegram",
    )

    await on_response_generated_summarize(
        event,
        conversations=conversations,
        summarizer=summarizer,
        user_settings=user_settings,
        settings=settings,
    )

    # Проверяем, что summarize НЕ был вызван
    summarize_mock.assert_not_called()
    replace_mock.assert_not_called()


async def test_summarize_exception_does_not_crash(
    user, conversations, summarizer, user_settings, settings, mocker
):
    """Исключение в суммаризаторе логируется как WARNING и не роняет подписчика."""
    # Заполняем историю до threshold
    for i in range(10):
        conversations.add_user_message("12345", f"message {i}")
        conversations.add_assistant_message("12345", f"response {i}")

    # Мокаем summarize с исключением
    mocker.patch.object(summarizer, "summarize", side_effect=Exception("summarizer failed"))

    event = ResponseGenerated(
        user=user,
        text="new response",
        conversation_id="12345",
        channel="telegram",
    )

    # Не должно падать
    await on_response_generated_summarize(
        event,
        conversations=conversations,
        summarizer=summarizer,
        user_settings=user_settings,
        settings=settings,
    )

    # История должна остаться без изменений
    history = conversations.get_history("12345")
    assert len(history) == 20  # 10 user + 10 assistant
