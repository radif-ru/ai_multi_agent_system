"""Маппер временных идентификаторов для файлов.

Заменяет полные пути к файлам на временные идентификаторы для защиты от
data leakage. См. задачу 4.1 спринта 05.

Использует общую таблицу file_contexts из ConversationStore для хранения
маппингов file_id → path.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)


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
    восстанавливать путь по идентификатору. Хранилище — общая таблица
    file_contexts из ConversationStore + in-memory кеш для быстрого доступа.
    """

    _ID_PREFIX: Final = "file_"
    _ID_LENGTH: Final = 12

    def __init__(self, *, db_path: Path = Path("data/file_contexts.db")) -> None:
        """Создать маппер с пустым хранилищем.

        Args:
            db_path: Путь к SQLite-файлу file_contexts.db (из ConversationStore).
        """
        self._id_to_path: dict[str, Path] = {}
        self._path_to_id: dict[Path, str] = {}
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle --------------------------------------------------------

    def init(self) -> None:
        """Инициализировать SQLite-хранилище и загрузить существующие маппинги."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)

        # Загружаем существующие маппинги из таблицы file_contexts
        try:
            cursor = self._conn.execute(
                "SELECT file_id, file_path FROM file_contexts WHERE file_id IS NOT NULL AND file_path IS NOT NULL"
            )
            for row in cursor:
                file_id, file_path_str = row
                if file_id and file_path_str:
                    path = Path(file_path_str)
                    if path.exists():  # Загружаем только если файл существует
                        self._id_to_path[file_id] = path
                        self._path_to_id[path] = file_id
            logger.info("FileIdMapper инициализирован: загружено %d маппингов", len(self._id_to_path))
        except sqlite3.OperationalError as exc:
            # Таблица ещё не создана или колонки нет - игнорируем
            logger.info("FileIdMapper: таблица file_contexts ещё не готова или старая схема: %s", exc)

    def close(self) -> None:
        """Закрыть соединение с БД."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- API --------------------------------------------------------------

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

        # Сохраняем маппинг в памяти
        self._id_to_path[file_id] = file_path
        self._path_to_id[file_path] = file_id

        # Сохранение в БД происходит через ConversationStore.save_file_context
        # при вызове из хендлеров. Здесь только сохраняем в памяти.

        return file_id

    def get_path(self, file_id: str) -> Path | None:
        """Восстановить путь по идентификатору.

        Args:
            file_id: Идентификатор файла.

        Returns:
            Путь к файлу или None, если ID не найден.
        """
        # Сначала ищем в памяти
        path = self._id_to_path.get(file_id)
        if path is not None:
            return path

        # Если нет в памяти, ищем в БД
        if self._conn is not None:
            try:
                cursor = self._conn.execute(
                    "SELECT file_path FROM file_contexts WHERE file_id = ?",
                    (file_id,),
                )
                row = cursor.fetchone()
                if row:
                    path_str = row[0]
                    if path_str:
                        path = Path(path_str)
                        if path.exists():  # Возвращаем только если файл существует
                            # Кешируем в памяти
                            self._id_to_path[file_id] = path
                            self._path_to_id[path] = file_id
                            return path
            except Exception as exc:  # noqa: BLE001
                logger.error("ошибка чтения маппинга из БД: %s", exc)

        return None

    def clear(self) -> None:
        """Очистить хранилище маппингов.

        Полезно для тестов или при сбросе состояния.
        """
        self._id_to_path.clear()
        self._path_to_id.clear()
        # Очистка БД происходит через ConversationStore.clear()
        # при вызове /new или reset. Здесь только очищаем память.
