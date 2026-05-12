"""Маппер временных идентификаторов для файлов.

Заменяет полные пути к файлам на временные идентификаторы для защиты от
data leakage. См. задачу 4.1 спринта 05.

Персистентный слой — колонки `file_id`/`file_path` в таблице `dialog_journal`
(`data/memory.db`); запись делает подписчик `on_message_received_journal`
(см. задачу 06.3-bis.3 и `_docs/memory.md` §2.6/§4.1). In-memory кеш —
для быстрых повторных обращений.
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


def file_id_not_found_message(file_id: str) -> str:
    """Единое объяснение для LLM, почему `file_id` недоступен.

    Чаще всего файл уже недоступен потому, что предыдущая сессия была
    закрыта командой `/new`: она архивирует диалог в долгосрочную память
    и удаляет загруженные файлы вместе с их `file_id`. См. `cmd_new` и
    `_cleanup_user_images` в `app/commands/registry.py`.
    """
    return (
        f"file_id {file_id} недоступен. Скорее всего, файл был удалён "
        "после команды /new: она закрывает сессию, оставляет только "
        "суммаризированный контекст в долгосрочной памяти и удаляет все "
        "загруженные файлы. Сообщи пользователю: чтобы снова работать с "
        "полным содержимым файла, ему нужно повторно прислать этот файл "
        "или изображение обычным сообщением в чат (прикрепить через "
        "скрепку или перетащить). Никакой специальной команды для "
        "загрузки (например, /upload) НЕ существует — просто отправь "
        "файл вложением. И предупреди, что следующая команда /new опять "
        "удалит загруженные файлы, поэтому использовать её стоит с "
        "осторожностью."
    )


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
    восстанавливать путь по идентификатору. Хранилище — таблица
    `dialog_journal` в `data/memory.db` (колонки `file_id`/`file_path`) +
    in-memory кеш для быстрого доступа.
    """

    _ID_PREFIX: Final = "file_"
    _ID_LENGTH: Final = 12

    def __init__(self, *, db_path: Path = Path("data/memory.db")) -> None:
        """Создать маппер с пустым хранилищем.

        Args:
            db_path: Путь к SQLite-файлу `data/memory.db` (таблица `dialog_journal`).
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

        # Загружаем существующие маппинги из dialog_journal (см. 06.3-bis.3).
        try:
            cursor = self._conn.execute(
                "SELECT DISTINCT file_id, file_path FROM dialog_journal "
                "WHERE file_id IS NOT NULL AND file_path IS NOT NULL"
            )
            for row in cursor:
                file_id, file_path_str = row
                if file_id and file_path_str:
                    path = Path(file_path_str)
                    if path.exists():  # Загружаем только если файл существует
                        self._id_to_path[file_id] = path
                        self._path_to_id[path] = file_id
            logger.info(
                "FileIdMapper инициализирован: загружено %d маппингов из dialog_journal",
                len(self._id_to_path),
            )
        except sqlite3.OperationalError as exc:
            # Таблица ещё не создана (DialogJournal.init() не вызывался).
            logger.info(
                "FileIdMapper: таблица dialog_journal ещё не готова: %s", exc,
            )

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

        # Запись в БД делает подписчик `on_message_received_journal` при
        # публикации `MessageReceived` из Telegram-хендлеров: колонки
        # `file_id`/`file_path` в `dialog_journal` (см. 06.3-bis.3).

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

        # Если нет в памяти, ищем в dialog_journal
        if self._conn is not None:
            try:
                cursor = self._conn.execute(
                    "SELECT file_path FROM dialog_journal "
                    "WHERE file_id = ? AND file_path IS NOT NULL "
                    "ORDER BY id DESC LIMIT 1",
                    (file_id,),
                )
                row = cursor.fetchone()
                if row:
                    path_str = row[0]
                    if path_str:
                        path = Path(path_str)
                        if path.exists():
                            self._id_to_path[file_id] = path
                            self._path_to_id[path] = file_id
                            return path
            except Exception as exc:  # noqa: BLE001
                logger.error("ошибка чтения маппинга из dialog_journal: %s", exc)

        return None

    def clear(self) -> None:
        """Очистить хранилище маппингов.

        Полезно для тестов или при сбросе состояния.
        """
        self._id_to_path.clear()
        self._path_to_id.clear()
        # Записи в `dialog_journal` живут до `mark_archived(...)` после
        # успешного `/new`; здесь сбрасываем только in-memory кеш.
