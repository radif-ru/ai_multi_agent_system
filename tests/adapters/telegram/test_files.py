"""Тесты утилит загрузки файлов из Telegram.

См. задачу 3.1 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from tempfile import TemporaryDirectory

import pytest

from app.adapters.telegram.files import FileTooLargeError, download_telegram_file


@pytest.fixture
def mock_bot():
    """Мок aiogram Bot."""
    bot = MagicMock()
    bot.get_file = AsyncMock()
    bot.download_file = AsyncMock()
    return bot


@pytest.fixture
def tmp_dir():
    """Временная директория для тестов."""
    with TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.mark.asyncio
async def test_download_telegram_file_success(mock_bot, tmp_dir):
    """Успешная загрузка файла."""
    # Настройка мока
    mock_file = MagicMock()
    mock_file.file_path = "documents/test.txt"
    mock_file.file_size = 1024  # 1 КБ
    mock_bot.get_file.return_value = mock_file

    # Мокаем download_file, чтобы он создавал файл
    async def mock_download(file_path, destination):
        destination.write_text("test content")

    mock_bot.download_file = AsyncMock(side_effect=mock_download)

    # Вызов
    result = await download_telegram_file(mock_bot, "file123", max_size_mb=20, tmp_dir=tmp_dir, user_id=None, mime_type="application/pdf")

    # Проверки
    assert isinstance(result, Path)
    assert result.exists()
    assert result.parent == tmp_dir
    assert result.suffix == ".pdf"
    mock_bot.get_file.assert_called_once_with("file123")
    mock_bot.download_file.assert_called_once()

    # Очистка
    result.unlink()


@pytest.mark.asyncio
async def test_download_telegram_file_too_large(mock_bot, tmp_dir):
    """Превышение лимита размера."""
    # Настройка мока: файл 25 МБ при лимите 20 МБ
    mock_file = MagicMock()
    mock_file.file_path = "documents/large.pdf"
    mock_file.file_size = 25 * 1024 * 1024  # 25 МБ
    mock_bot.get_file.return_value = mock_file

    # Вызов и проверка исключения
    with pytest.raises(FileTooLargeError) as exc_info:
        await download_telegram_file(mock_bot, "file456", max_size_mb=20, tmp_dir=tmp_dir, user_id=None)

    assert exc_info.value.file_size_mb == 25
    assert exc_info.value.max_size_mb == 20
    assert "25 МБ превышает лимит 20 МБ" in str(exc_info.value)


@pytest.mark.asyncio
async def test_download_telegram_file_download_error(mock_bot, tmp_dir):
    """Ошибка при скачивании файла."""
    # Настройка мока
    mock_file = MagicMock()
    mock_file.file_path = "documents/test.txt"
    mock_file.file_size = 1024
    mock_bot.get_file.return_value = mock_file
    mock_bot.download_file = AsyncMock(side_effect=Exception("Network error"))

    # Вызов и проверка исключения
    with pytest.raises(Exception, match="Network error"):
        await download_telegram_file(mock_bot, "file789", max_size_mb=20, tmp_dir=tmp_dir, user_id=None)


@pytest.mark.asyncio
async def test_download_telegram_file_no_size_info(mock_bot, tmp_dir):
    """Загрузка файла без информации о размере (file_size=None)."""
    # Настройка мока: file_size=None (Telegram иногда не предоставляет размер)
    mock_file = MagicMock()
    mock_file.file_path = "documents/test.txt"
    mock_file.file_size = None
    mock_bot.get_file.return_value = mock_file

    # Мокаем download_file, чтобы он создавал файл
    async def mock_download(file_path, destination):
        destination.write_text("test content")

    mock_bot.download_file = AsyncMock(side_effect=mock_download)

    # Вызов - должно сработать без проверки размера
    result = await download_telegram_file(mock_bot, "file000", max_size_mb=20, tmp_dir=tmp_dir, user_id=None, mime_type="text/plain")

    # Проверки
    assert isinstance(result, Path)
    assert result.exists()
    assert result.parent == tmp_dir
    assert result.suffix == ".txt"
    mock_bot.get_file.assert_called_once_with("file000")
    mock_bot.download_file.assert_called_once()

    # Очистка
    result.unlink()
