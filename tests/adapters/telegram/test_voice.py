"""Тесты handler для голосовых сообщений.

См. задачу 3.4 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.files import FileTooLargeError
from app.adapters.telegram.handlers.messages import (
    FILE_TOO_LARGE_REPLY,
    VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY,
    handle_voice,
)
from app.core.events import EventBus, MessageReceived, ResponseGenerated


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
        message.answer.assert_called_once_with(VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY, parse_mode=None)

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
        message.answer.assert_called_once_with(VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY, parse_mode=None)

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

    async def mock_download(bot, file_id, *, max_size_mb, tmp_dir=None, user_id=None, mime_type=None):
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
        message.answer.assert_called_once_with(FILE_TOO_LARGE_REPLY, parse_mode=None)

        # Проверяем, что executor не вызывался
        mock_conversations.add_user_message.assert_not_called()
    finally:
        messages.is_transcriber_available = original_available
        messages.download_telegram_file = original_download


@pytest.fixture
def event_bus_with_conversations(mock_conversations):
    """Создаёт EventBus с подписчиками для ConversationStore и мок для users."""
    event_bus = EventBus()
    from app.services.conversation_subscriber import on_message_received, on_response_generated
    from functools import partial
    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=mock_conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=mock_conversations))

    mock_user = MagicMock()
    mock_user.external_id = "123"
    mock_users = MagicMock()
    mock_users.get_or_create = AsyncMock(return_value=(mock_user, False))

    return event_bus, mock_users


@pytest.mark.asyncio
async def test_handle_voice_publishes_event_with_kind_and_file_meta(
    mock_settings,
    mock_user_settings,
    mock_conversations,
    mock_summarizer,
    mock_executor,
    mock_llm,
    mock_semantic_memory,
    event_bus_with_conversations,
    tmp_path: Path,
) -> None:
    """В MessageReceived проброшены kind=voice, file_id и file_path (для dialog_journal)."""
    from app.adapters.telegram.handlers import messages

    event_bus, mock_users = event_bus_with_conversations
    received: list[MessageReceived] = []

    async def recorder(event: MessageReceived) -> None:
        received.append(event)

    event_bus.subscribe(MessageReceived, recorder)

    test_file = tmp_path / "voice.ogg"
    test_file.write_bytes(b"fake")

    original_available = messages.is_transcriber_available
    original_download = messages.download_telegram_file
    original_handle = messages.handle_user_task
    original_transcriber = messages.Transcriber

    async def mock_download(bot, file_id, *, max_size_mb, tmp_dir=None, user_id=None, mime_type=None):
        return test_file

    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = "привет"

    messages.is_transcriber_available = lambda: True
    messages.download_telegram_file = mock_download
    messages.Transcriber = MagicMock(return_value=fake_transcriber)
    messages.handle_user_task = AsyncMock(return_value="ok")

    try:
        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.chat = MagicMock(id=456)
        message.voice = MagicMock(file_id="voice123", mime_type="audio/ogg")
        message.document = None
        message.reply_to_message = None
        message.message_id = 1
        message.bot = MagicMock()
        message.answer = AsyncMock()

        await handle_voice(
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

        assert len(received) == 1
        ev = received[0]
        assert ev.kind == "voice"
        assert ev.file_id
        assert ev.file_path == str(test_file)
    finally:
        messages.is_transcriber_available = original_available
        messages.download_telegram_file = original_download
        messages.handle_user_task = original_handle
        messages.Transcriber = original_transcriber
