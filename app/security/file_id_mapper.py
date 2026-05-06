"""Маппер временных идентификаторов для файлов.

Заменяет полные пути к файлам на временные идентификаторы для защиты от
data leakage. См. задачу 4.1 спринта 05.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Final


# Глобальный экземпляр для использования в хендлерах и tools
_global_mapper: FileIdMapper | None = None


def get_global_mapper() -> FileIdMapper:
    """Получить глобальный экземпляр FileIdMapper."""
    global _global_mapper
    if _global_mapper is None:
        _global_mapper = FileIdMapper()
    return _global_mapper


def clear_global_mapper() -> None:
    """Очистить глобальный экземпляр FileIdMapper.

    Полезно для тестов.
    """
    global _global_mapper
    if _global_mapper is not None:
        _global_mapper.clear()
        _global_mapper = None


class FileIdMapper:
    """Маппер временных идентификаторов для файлов.

    Генерирует уникальные временные идентификаторы для файлов и умеет
    восстанавливать путь по идентификатору. Хранилище — in-memory dict.
    """

    _ID_PREFIX: Final = "file_"
    _ID_LENGTH: Final = 12

    def __init__(self) -> None:
        """Создать маппер с пустым хранилищем."""
        self._id_to_path: dict[str, Path] = {}
        self._path_to_id: dict[Path, str] = {}

    def generate_id(self, file_path: Path) -> str:
        """Сгенерировать уникальный ID для файла.

        Если ID уже был сгенерирован для этого пути, возвращает существующий.

        Args:
            file_path: Путь к файлу.

        Returns:
            Уникальный идентификатор (например, `file_abc123def456`).
        """
        # Проверяем, есть ли уже ID для этого пути
        if file_path in self._path_to_id:
            return self._path_to_id[file_path]

        # Генерируем уникальный ID
        while True:
            file_id = f"{self._ID_PREFIX}{secrets.token_hex(self._ID_LENGTH)}"
            if file_id not in self._id_to_path:
                break

        # Сохраняем маппинг
        self._id_to_path[file_id] = file_path
        self._path_to_id[file_path] = file_id

        return file_id

    def get_path(self, file_id: str) -> Path | None:
        """Восстановить путь по идентификатору.

        Args:
            file_id: Идентификатор файла.

        Returns:
            Путь к файлу или None, если ID не найден.
        """
        return self._id_to_path.get(file_id)

    def clear(self) -> None:
        """Очистить хранилище маппингов.

        Полезно для тестов или при сбросе состояния.
        """
        self._id_to_path.clear()
        self._path_to_id.clear()
