"""Тесты handler для фотографий.

См. задачу 3.5 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.files import FileTooLargeError
from app.adapters.telegram.handlers.messages import VISION_UNAVAILABLE_REPLY, handle_photo
from app.core.events import EventBus, MessageReceived, ResponseGenerated


@pytest.fixture
def mock_settings():
    """Мок Settings."""
    settings = MagicMock()
    settings.telegram_max_file_mb = 20
    settings.history_summary_threshold = 10
    settings.vision_model = None
    settings.tmp_files_dir = Path("tmp")
    return settings


@pytest.fixture
def mock_user_settings():
    """Мок UserSettingsRegistry."""
    registry = MagicMock()
    registry.get_model.return_value = "qwen3.5:4b"
    return registry


@pytest.fixture
def mock_conversations():
    """Мок ConversationStore."""
    store = MagicMock()
    store.get_history.return_value = []
    return store


@pytest.fixture
def mock_summarizer():
    """Мок Summarizer."""
    return MagicMock()


@pytest.fixture
def mock_executor():
    """Мок Executor."""
    return MagicMock()


@pytest.fixture
def mock_llm():
    """Мок OllamaClient."""
    return MagicMock()


@pytest.fixture
def mock_semantic_memory():
    """Мок SemanticMemory."""
    return MagicMock()


@pytest.fixture
def event_bus_with_conversations(mock_conversations):
    """Создаёт EventBus с подписчиками для ConversationStore и мок для users."""
    event_bus = EventBus()
    from app.services.conversation_subscriber import on_message_received, on_response_generated
    from functools import partial
    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=mock_conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=mock_conversations))

    # Мок для users
    mock_user = MagicMock()
    mock_user.external_id = "123"
    mock_users = MagicMock()
    mock_users.get_or_create = AsyncMock(return_value=(mock_user, False))

    return event_bus, mock_users


@pytest.mark.asyncio
async def test_handle_photo_vision_model_not_configured(
    mock_settings,
    mock_user_settings,
    mock_conversations,
    mock_summarizer,
    mock_executor,
    mock_llm,
    mock_semantic_memory,
) -> None:
    """Vision-модель не настроена."""
    # Создаём мок Message с фото
    message = MagicMock()
    message.from_user = MagicMock(id=123)
    message.chat = MagicMock(id=456)
    message.photo = [MagicMock(file_id="photo123")]
    message.bot = MagicMock()
    message.answer = AsyncMock()

    # Вызываем handler
    await handle_photo(
        message,
        settings=mock_settings,
        user_settings=mock_user_settings,
        conversations=mock_conversations,
        summarizer=mock_summarizer,
        executor=mock_executor,
        llm=mock_llm,
        semantic_memory=mock_semantic_memory,
    )

    # Проверяем, что отправлено сообщение о недоступности
    message.answer.assert_called_once_with(VISION_UNAVAILABLE_REPLY, parse_mode=None)

    # Проверяем, что executor не вызывался
    mock_conversations.add_user_message.assert_not_called()


@pytest.mark.asyncio
async def test_handle_photo_success(
    mock_settings,
    mock_user_settings,
    mock_conversations,
    mock_summarizer,
    mock_executor,
    mock_llm,
    mock_semantic_memory,
    event_bus_with_conversations,
    mocker,
) -> None:
    """Успешная обработка фото (без реальной vision - только проверка потока)."""
    from app.adapters.telegram.handlers import messages

    # Настраиваем vision-модель
    mock_settings.vision_model = "llava:7b"

    # Мокаем Vision в том месте, откуда его импортирует handler
    mock_vision_instance = MagicMock()
    mock_vision_instance.describe = AsyncMock(return_value="На фото кот")
    mocker.patch("app.adapters.telegram.handlers.messages.Vision", return_value=mock_vision_instance)

    # Мокаем download_telegram_file
    original_download = messages.download_telegram_file

    async def mock_download(bot, file_id, *, max_size_mb, tmp_dir, user_id=None, mime_type=None):
        from pathlib import Path
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            return Path(f.name)

    messages.download_telegram_file = mock_download

    try:
        # Мокаем executor.run
        mock_executor.run = AsyncMock(return_value="Ответ на фото")

        # Создаём мок Message с фото
        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.chat = MagicMock(id=456)
        message.photo = [MagicMock(file_id="photo123")]
        message.caption = "Мой кот"
        message.bot = MagicMock()
        message.answer = AsyncMock()
        # Добавляем event_bus и users в dispatcher
        event_bus, mock_users = event_bus_with_conversations
        message.bot.get_current_dispatcher.return_value.get.side_effect = lambda key: {
            "users": mock_users,
            "event_bus": event_bus,
        }.get(key)

        # Вызываем handler
        await handle_photo(
            message,
            settings=mock_settings,
            user_settings=mock_user_settings,
            conversations=mock_conversations,
            summarizer=mock_summarizer,
            executor=mock_executor,
            llm=mock_llm,
            semantic_memory=mock_semantic_memory,
        )

        # Проверяем, что executor.run был вызван
        mock_executor.run.assert_called_once()
    finally:
        messages.download_telegram_file = original_download
