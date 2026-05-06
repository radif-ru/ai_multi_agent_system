"""Тесты handler для фотографий.

См. задачу 3.5 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.files import FileTooLargeError
from app.adapters.telegram.handlers.messages import handle_photo
from app.core.events import EventBus, MessageReceived, ResponseGenerated


@pytest.fixture
def mock_settings():
    """Мок Settings."""
    settings = MagicMock()
    settings.telegram_max_file_mb = 20
    settings.history_summary_threshold = 10
    settings.tmp_base_dir = Path("tmp")
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
    """Успешная обработка фото - передача агенту для выбора между vision и OCR."""
    from app.adapters.telegram.handlers import messages

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
        # Мокаем handle_user_task
        original_handle_user_task = messages.handle_user_task
        messages.handle_user_task = AsyncMock(return_value="Ответ на фото")

        # Создаём мок Message с фото
        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.chat = MagicMock(id=456)
        message.photo = [MagicMock(file_id="photo123")]
        message.caption = "Мой кот"
        message.bot = MagicMock()
        message.answer = AsyncMock()
        event_bus, mock_users = event_bus_with_conversations

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
            users=mock_users,
            event_bus=event_bus,
        )

        # Проверяем, что handle_user_task был вызван
        messages.handle_user_task.assert_called_once()
        
        # Проверяем, что в goal есть file_id
        call_args = messages.handle_user_task.call_args
        goal = call_args[0][0]  # Первый позиционный аргумент - это goal
        assert "file_id:" in goal
        assert "describe_image" in goal or "ocr_image" in goal
    finally:
        messages.download_telegram_file = original_download
        messages.handle_user_task = original_handle_user_task
