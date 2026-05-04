"""Утилиты для работы с файлами из Telegram.

См. задачу 3.1 спринта 02: загрузка файла с лимитами размера.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.types import File

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class FileTooLargeError(Exception):
    """Файл превышает допустимый размер."""

    def __init__(self, file_size_mb: int, max_size_mb: int) -> None:
        super().__init__(
            f"Размер файла {file_size_mb} МБ превышает лимит {max_size_mb} МБ"
        )
        self.file_size_mb = file_size_mb
        self.max_size_mb = max_size_mb


async def download_telegram_file(
    bot: Bot,
    file_id: str,
    *,
    max_size_mb: int,
    tmp_dir: Path,
    user_id: int | None = None,
    mime_type: str | None = None,
) -> Path:
    """Скачать файл из Telegram с проверкой размера.

    Args:
        bot: Экземпляр aiogram Bot.
        file_id: Идентификатор файла в Telegram.
        max_size_mb: Максимальный размер файла в мегабайтах.
        tmp_dir: Директория для временных файлов (Settings.tmp_base_dir).
        user_id: ID пользователя для создания подкаталога.
        mime_type: MIME-type файла из Telegram (для определения расширения).

    Returns:
        Путь к скачанному временному файлу.

    Raises:
        FileTooLargeError: Если размер файла превышает лимит.
        Exception: При ошибке скачивания из Telegram.
    """
    # Получаем информацию о файле
    file_info: File = await bot.get_file(file_id)

    # Проверяем размер (если доступен)
    if file_info.file_size is not None:
        file_size_mb = file_info.file_size / (1024 * 1024)
        if file_size_mb > max_size_mb:
            logger.warning(
                "Файл %s превышает лимит: %.2f МБ > %d МБ",
                file_id,
                file_size_mb,
                max_size_mb,
            )
            raise FileTooLargeError(int(file_size_mb), max_size_mb)

    # Определяем расширение по mime_type
    extension = ""
    if mime_type:
        mime_to_ext = {
            "application/pdf": ".pdf",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
        }
        extension = mime_to_ext.get(mime_type, "")

    # Скачиваем во временный файл в указанной директории
    try:
        # Создаём директорию пользователя, если указан user_id
        if user_id is not None:
            tmp_dir = tmp_dir / str(user_id)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Создаём уникальное имя файла с расширением
        file_name = f"{file_id}_{uuid.uuid4().hex[:8]}{extension}"
        tmp_path = tmp_dir / file_name

        await bot.download_file(file_info.file_path, tmp_path)
        logger.info(
            "Файл %s (%d байт) скачан в %s",
            file_id,
            file_info.file_size or 0,
            tmp_path,
        )
        return tmp_path
    except Exception as e:
        logger.error("Ошибка скачивания файла %s: %s", file_id, e)
        raise
