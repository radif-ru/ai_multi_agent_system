"""Тесты handler для голосовых сообщений.

См. задачу 3.4 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.files import FileTooLargeError
from app.adapters.telegram.handlers.messages import (
    VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY,
    handle_voice,
)
from app.services.transcribe import TranscriberUnavailableError


@pytest.fixture
def mock_settings():
    """Мок Settings."""
    settings = MagicMock()
    settings.telegram_max_file_mb = 20
    settings.history_summary_threshold = 10
    settings.whisper_model = "base"
    settings.whisper_language = "ru"
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


@pytest.mark.asyncio
async def test_handle_voice_success(
    mock_settings,
    mock_user_settings,
    mock_conversations,
    mock_summarizer,
    mock_executor,
    mock_llm,
    mock_semantic_memory,
    tmp_path: Path,
) -> None:
    """Успешная обработка голосового сообщения (без реальной транскрипции)."""
    from app.adapters.telegram.handlers import messages

    # Мокаем is_transcriber_available как False, чтобы пропустить реальную транскрипцию
    original_available = messages.is_transcriber_available
    messages.is_transcriber_available = lambda: False

    try:
        # Создаём мок Message с голосом
        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.chat = MagicMock(id=456)
        message.voice = MagicMock(file_id="voice123")
        message.bot = MagicMock()
        message.answer = AsyncMock()

        # Вызываем handler
        await handle_voice(
            message,
            settings=mock_settings,
            user_settings=mock_user_settings,
            conversations=mock_conversations,
            summarizer=mock_summarizer,
            executor=mock_executor,
            llm=mock_llm,
            semantic_memory=mock_semantic_memory,
        )

        # При недоступности transcriber должно быть отправлено сообщение
        message.answer.assert_called_once()
        assert "недоступно" in message.answer.call_args[0][0].lower()

        # Executor не должен вызываться
        mock_conversations.add_user_message.assert_not_called()
    finally:
        messages.is_transcriber_available = original_available


@pytest.mark.asyncio
async def test_handle_voice_transcriber_unavailable(
    mock_settings,
    mock_user_settings,
    mock_conversations,
    mock_summarizer,
    mock_executor,
    mock_llm,
    mock_semantic_memory,
) -> None:
    """Transcriber недоступен."""
    from app.adapters.telegram.handlers import messages

    # Мокаем is_transcriber_available как False
    original_available = messages.is_transcriber_available
    messages.is_transcriber_available = lambda: False

    try:
        # Создаём мок Message с голосом
        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.chat = MagicMock(id=456)
        message.voice = MagicMock(file_id="voice123")
        message.bot = MagicMock()
        message.answer = AsyncMock()

        # Вызываем handler
        await handle_voice(
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
        message.answer.assert_called_once_with(VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY)

        # Проверяем, что executor не вызывался
        mock_conversations.add_user_message.assert_not_called()
    finally:
        messages.is_transcriber_available = original_available


@pytest.mark.asyncio
async def test_handle_voice_too_large(
    mock_settings,
    mock_user_settings,
    mock_conversations,
    mock_summarizer,
    mock_executor,
    mock_llm,
    mock_semantic_memory,
) -> None:
    """Превышение лимита размера голосового файла."""
    from app.adapters.telegram.handlers import messages

    # Мокаем is_transcriber_available
    original_available = messages.is_transcriber_available
    messages.is_transcriber_available = lambda: True

    # Мокаем download_telegram_file
    original_download = messages.download_telegram_file

    async def mock_download(bot, file_id, *, max_size_mb, tmp_dir=None, user_id=None):
        raise FileTooLargeError(file_size_mb=25, max_size_mb=20)

    messages.download_telegram_file = mock_download

    try:
        # Создаём мок Message с голосом
        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.chat = MagicMock(id=456)
        message.voice = MagicMock(file_id="voice123")
        message.bot = MagicMock()
        message.answer = AsyncMock()

        # Вызываем handler
        await handle_voice(
            message,
            settings=mock_settings,
            user_settings=mock_user_settings,
            conversations=mock_conversations,
            summarizer=mock_summarizer,
            executor=mock_executor,
            llm=mock_llm,
            semantic_memory=mock_semantic_memory,
        )

        # Проверяем, что отправлено сообщение о превышении
        message.answer.assert_called_once()

        # Проверяем, что executor не вызывался
        mock_conversations.add_user_message.assert_not_called()
    finally:
        messages.is_transcriber_available = original_available
        messages.download_telegram_file = original_download
