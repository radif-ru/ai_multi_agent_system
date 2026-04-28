"""Тесты утилит загрузки файлов из Telegram.

См. задачу 3.1 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.files import FileTooLargeError, download_telegram_file


@pytest.fixture
def mock_bot():
    """Мок aiogram Bot."""
    bot = MagicMock()
    bot.get_file = AsyncMock()
    bot.download_file = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_download_telegram_file_success(mock_bot):
    """Успешная загрузка файла."""
    # Настройка мока
    mock_file = MagicMock()
    mock_file.file_path = "documents/test.txt"
    mock_file.file_size = 1024  # 1 КБ
    mock_bot.get_file.return_value = mock_file

    # Вызов
    result = await download_telegram_file(mock_bot, "file123", max_size_mb=20)

    # Проверки
    assert isinstance(result, Path)
    assert result.exists()
    mock_bot.get_file.assert_called_once_with("file123")
    mock_bot.download_file.assert_called_once()

    # Очистка
    result.unlink()


@pytest.mark.asyncio
async def test_download_telegram_file_too_large(mock_bot):
    """Превышение лимита размера."""
    # Настройка мока: файл 25 МБ при лимите 20 МБ
    mock_file = MagicMock()
    mock_file.file_path = "documents/large.pdf"
    mock_file.file_size = 25 * 1024 * 1024  # 25 МБ
    mock_bot.get_file.return_value = mock_file

    # Вызов и проверка исключения
    with pytest.raises(FileTooLargeError) as exc_info:
        await download_telegram_file(mock_bot, "file456", max_size_mb=20)

    assert exc_info.value.file_size_mb == 25
    assert exc_info.value.max_size_mb == 20
    assert "25 МБ превышает лимит 20 МБ" in str(exc_info.value)


@pytest.mark.asyncio
async def test_download_telegram_file_download_error(mock_bot):
    """Ошибка при скачивании файла."""
    # Настройка мока
    mock_file = MagicMock()
    mock_file.file_path = "documents/test.txt"
    mock_file.file_size = 1024
    mock_bot.get_file.return_value = mock_file
    mock_bot.download_file.side_effect = Exception("Network error")

    # Вызов и проверка исключения
    with pytest.raises(Exception, match="Network error"):
        await download_telegram_file(mock_bot, "file789", max_size_mb=20)


@pytest.mark.asyncio
async def test_download_telegram_file_no_size_info(mock_bot):
    """Загрузка файла без информации о размере (file_size=None)."""
    # Настройка мока: file_size=None (Telegram иногда не предоставляет размер)
    mock_file = MagicMock()
    mock_file.file_path = "documents/test.txt"
    mock_file.file_size = None
    mock_bot.get_file.return_value = mock_file

    # Вызов - должно сработать без проверки размера
    result = await download_telegram_file(mock_bot, "file000", max_size_mb=20)

    # Проверки
    assert isinstance(result, Path)
    assert result.exists()
    mock_bot.get_file.assert_called_once_with("file000")
    mock_bot.download_file.assert_called_once()

    # Очистка
    result.unlink()
