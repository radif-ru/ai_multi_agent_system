"""Краткосрочная память: in-memory история диалога per-user.

См. `_docs/memory.md` §2 (`_messages` — rolling-буфер для LLM)
и §2.5 (`_session_log` — append-only полный лог сессии для `/new`).
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any


Message = dict[str, Any]

logger = logging.getLogger(__name__)


class ConversationStore:
    """In-memory история сообщений и conversation_id для каждого пользователя.

    Внутри два параллельных буфера на каждого пользователя:

    - ``_messages`` — rolling-буфер для контекста LLM. Урезается FIFO по
      ``max_messages`` и сжимается ``replace_with_summary`` при срабатывании
      in-session порога суммаризации.
    - ``_session_log`` — append-only лог всех ``user``/``assistant`` сообщений
      текущей сессии. Не подвержен compaction; ``replace_with_summary`` его
      не трогает. Используется ``cmd_new`` → ``Archiver`` для архивирования
      ПОЛНОЙ истории при ``/new``. Имеет верхнюю страховку
      ``session_log_max_messages``.
    """

    def __init__(
        self,
        *,
        max_messages: int,
        session_log_max_messages: int = 1000,
        file_contexts_db: Path = Path("data/file_contexts.db"),
    ) -> None:
        if max_messages <= 0:
            raise ValueError("max_messages must be > 0")
        if session_log_max_messages <= 0:
            raise ValueError("session_log_max_messages must be > 0")
        self._max_messages = max_messages
        self._session_log_max = session_log_max_messages
        self._messages: dict[int, list[Message]] = {}
        self._session_log: dict[int, list[Message]] = {}
        self._conversation_ids: dict[int, str] = {}
        self._file_contexts: dict[int, dict[int, str]] = {}
        self._file_contexts_db = file_contexts_db
        self._init_file_contexts_db()

    def _init_file_contexts_db(self) -> None:
        """Создать таблицу для контекстов файлов."""
        self._file_contexts_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._file_contexts_db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_contexts (
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    file_type TEXT NOT NULL,
                    context TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, message_id)
                )
                """
            )
            conn.commit()

    # -- история ----------------------------------------------------------

    def get_history(self, user_id: int) -> list[Message]:
        """Вернуть копию истории; внешние мутации не влияют на стор."""
        return [dict(m) for m in self._messages.get(user_id, [])]

    def get_session_log(self, user_id: int) -> list[Message]:
        """Вернуть копию ПОЛНОГО лога сессии (без in-session compaction).

        См. `_docs/memory.md` §2.5. Используется `cmd_new` для архивации.
        """
        return [dict(m) for m in self._session_log.get(user_id, [])]

    def add_user_message(self, user_id: int, text: str) -> None:
        msg: Message = {"role": "user", "content": text}
        self._append(user_id, msg)
        self._append_session_log(user_id, msg)

    def add_assistant_message(self, user_id: int, text: str) -> None:
        msg: Message = {"role": "assistant", "content": text}
        self._append(user_id, msg)
        self._append_session_log(user_id, msg)

    def add_system_message(self, user_id: int, text: str) -> None:
        # System-сообщения — это технические подсказки/инжекты, в полный лог
        # сессии они не попадают (см. `_docs/memory.md` §2.5).
        self._append(user_id, {"role": "system", "content": text})

    def replace_with_summary(
        self, user_id: int, summary: str, *, kept_tail: int = 2
    ) -> None:
        """Заменить всё, кроме последних kept_tail сообщений, одним system-резюме.

        Не трогает `_session_log` — это in-session оптимизация контекста для
        LLM, а не редактирование исходного диалога.
        """
        if kept_tail < 0:
            raise ValueError("kept_tail must be >= 0")
        history = self._messages.get(user_id, [])
        tail = history[-kept_tail:] if kept_tail else []
        summary_msg: Message = {
            "role": "system",
            "content": f"Краткое резюме предыдущей части диалога: {summary}",
        }
        self._messages[user_id] = [summary_msg, *tail]

    def clear(self, user_id: int) -> None:
        self._messages.pop(user_id, None)
        self._session_log.pop(user_id, None)
        self._conversation_ids.pop(user_id, None)
        self._file_contexts.pop(user_id, None)
        # Очищаем контексты файлов из БД
        try:
            with sqlite3.connect(self._file_contexts_db) as conn:
                conn.execute(
                    "DELETE FROM file_contexts WHERE user_id = ?",
                    (user_id,),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("ошибка очистки контекстов из БД: %s", exc)

    # -- file contexts ----------------------------------------------------

    def save_file_context(
        self, user_id: int, message_id: int, file_type: str, context: str
    ) -> None:
        """Сохранить контекст файла для ответов на конкретный файл."""
        # Сохраняем в памяти для быстрого доступа
        if user_id not in self._file_contexts:
            self._file_contexts[user_id] = {}
        self._file_contexts[user_id][message_id] = context
        # Сохраняем в БД для персистентности
        try:
            with sqlite3.connect(self._file_contexts_db) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO file_contexts (user_id, message_id, file_type, context)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, message_id, file_type, context),
                )
                conn.commit()
            logger.info("сохранён контекст файла user_id=%s message_id=%s file_type=%s", user_id, message_id, file_type)
        except Exception as exc:  # noqa: BLE001
            logger.error("ошибка сохранения контекста в БД: %s", exc)

    def get_file_context(self, user_id: int, message_id: int) -> str | None:
        """Получить контекст файла по message_id."""
        # Сначала ищем в памяти
        ctx = self._file_contexts.get(user_id, {}).get(message_id)
        if ctx:
            logger.info("получен контекст файла из памяти user_id=%s message_id=%s", user_id, message_id)
            return ctx
        # Если нет в памяти, ищем в БД
        try:
            with sqlite3.connect(self._file_contexts_db) as conn:
                cursor = conn.execute(
                    """
                    SELECT context FROM file_contexts
                    WHERE user_id = ? AND message_id = ?
                    """,
                    (user_id, message_id),
                )
                row = cursor.fetchone()
                if row:
                    ctx = row[0]
                    # Кешируем в памяти
                    if user_id not in self._file_contexts:
                        self._file_contexts[user_id] = {}
                    self._file_contexts[user_id][message_id] = ctx
                    logger.info("получен контекст файла из БД user_id=%s message_id=%s", user_id, message_id)
                    return ctx
        except Exception as exc:  # noqa: BLE001
            logger.error("ошибка чтения контекста из БД: %s", exc)
        logger.warning("контекст файла не найден user_id=%s message_id=%s", user_id, message_id)
        return None

    # -- conversation_id --------------------------------------------------

    def current_conversation_id(self, user_id: int) -> str:
        cid = self._conversation_ids.get(user_id)
        if cid is None:
            cid = uuid.uuid4().hex
            self._conversation_ids[user_id] = cid
        return cid

    def rotate_conversation_id(self, user_id: int) -> str:
        """Ротация conversation_id и сброс полного лога сессии.

        Возвращает старый id (или пустую строку, если не было). Полный лог
        сессии относится к закрываемой сессии и обнуляется здесь же — новая
        сессия начинается с пустого `_session_log`.
        """
        old = self._conversation_ids.get(user_id, "")
        self._conversation_ids[user_id] = uuid.uuid4().hex
        self._session_log.pop(user_id, None)
        return old

    # -- internals --------------------------------------------------------

    def _append(self, user_id: int, msg: Message) -> None:
        bucket = self._messages.setdefault(user_id, [])
        bucket.append(msg)
        overflow = len(bucket) - self._max_messages
        if overflow > 0:
            del bucket[:overflow]

    def _append_session_log(self, user_id: int, msg: Message) -> None:
        bucket = self._session_log.setdefault(user_id, [])
        bucket.append(msg)
        overflow = len(bucket) - self._session_log_max
        if overflow > 0:
            logger.warning(
                "session_log overflow user_id=%s drop_head=%d limit=%d",
                user_id,
                overflow,
                self._session_log_max,
            )
            del bucket[:overflow]
