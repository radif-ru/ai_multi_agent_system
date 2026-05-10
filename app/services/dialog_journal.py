"""Append-only журнал диалога для восстановления при рестарте.

См. `_docs/memory.md` §4. Журнал лежит в той же `memory.db`, что и
`SemanticMemory`, но в отдельной таблице и через отдельное соединение
(без расширения `sqlite-vec`). Каждое сообщение сессии (текст пользователя,
ответ агента, метаданные файла) записывается строкой; при `/new` или
успешной фоновой архивации строки сессии помечаются `archived_at`.

Инвариант: строки с `archived_at IS NULL` — это незавершённый «долг»,
который должен быть переведён в `memory_chunks` фоновой задачей при старте
процесса (см. задачу 3.4 спринта 06).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DialogJournal:
    """Слой над `sqlite3` поверх `data/memory.db`.

    API синхронный по сути; внешние корутины оборачивают вызовы в
    `asyncio.to_thread`, как в `SemanticMemory`.
    """

    _ALLOWED_KINDS = ("text", "document", "voice", "image", "system")
    _ALLOWED_ROLES = ("user", "assistant", "system")

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle --------------------------------------------------------

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dialog_journal (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                chat_id         INTEGER NOT NULL,
                conversation_id TEXT    NOT NULL,
                role            TEXT    NOT NULL,    -- user | assistant | system
                kind            TEXT    NOT NULL,    -- text | document | voice | image | system
                content         TEXT    NOT NULL,
                file_id         TEXT,
                file_path       TEXT,
                created_at      TEXT    NOT NULL,
                archived_at     TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_journal_pending
                ON dialog_journal(user_id, conversation_id, archived_at);
            CREATE INDEX IF NOT EXISTS ix_journal_created
                ON dialog_journal(created_at);
            """
        )
        conn.commit()
        self._conn = conn

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    # -- API --------------------------------------------------------------

    async def append(
        self,
        *,
        user_id: int,
        chat_id: int,
        conversation_id: str,
        role: str,
        kind: str,
        content: str,
        file_id: str | None = None,
        file_path: str | None = None,
    ) -> int:
        if role not in self._ALLOWED_ROLES:
            raise ValueError(f"role must be one of {self._ALLOWED_ROLES}, got {role!r}")
        if kind not in self._ALLOWED_KINDS:
            raise ValueError(f"kind must be one of {self._ALLOWED_KINDS}, got {kind!r}")
        return await asyncio.to_thread(
            self._append_sync,
            user_id, chat_id, conversation_id, role, kind, content, file_id, file_path,
        )

    def _append_sync(
        self,
        user_id: int,
        chat_id: int,
        conversation_id: str,
        role: str,
        kind: str,
        content: str,
        file_id: str | None,
        file_path: str | None,
    ) -> int:
        conn = self._require_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO dialog_journal
                    (user_id, chat_id, conversation_id, role, kind,
                     content, file_id, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    int(user_id), int(chat_id), str(conversation_id),
                    role, kind, content, file_id, file_path, _now_iso(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        except Exception:
            conn.rollback()
            raise

    async def pending_conversations(self) -> list[tuple[int, int, str]]:
        """Сессии, в которых есть хотя бы одна строка с `archived_at IS NULL`.

        Возвращает упорядоченный по времени появления список
        `(user_id, chat_id, conversation_id)`.
        """
        return await asyncio.to_thread(self._pending_sync)

    def _pending_sync(self) -> list[tuple[int, int, str]]:
        conn = self._require_conn()
        rows = conn.execute(
            """
            SELECT user_id, chat_id, conversation_id, MIN(created_at) AS first_at
            FROM dialog_journal
            WHERE archived_at IS NULL
            GROUP BY user_id, chat_id, conversation_id
            ORDER BY first_at ASC;
            """
        ).fetchall()
        return [(int(r[0]), int(r[1]), str(r[2])) for r in rows]

    async def read_conversation(
        self, user_id: int, conversation_id: str
    ) -> list[dict[str, Any]]:
        """Все строки одной сессии в хронологическом порядке."""
        return await asyncio.to_thread(
            self._read_conversation_sync, user_id, conversation_id
        )

    def _read_conversation_sync(
        self, user_id: int, conversation_id: str
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        rows = conn.execute(
            """
            SELECT id, role, kind, content, file_id, file_path, created_at, archived_at
            FROM dialog_journal
            WHERE user_id = ? AND conversation_id = ?
            ORDER BY id ASC;
            """,
            (int(user_id), str(conversation_id)),
        ).fetchall()
        return [
            {
                "id": r[0],
                "role": r[1],
                "kind": r[2],
                "content": r[3],
                "file_id": r[4],
                "file_path": r[5],
                "created_at": r[6],
                "archived_at": r[7],
            }
            for r in rows
        ]

    async def mark_archived(self, user_id: int, conversation_id: str) -> int:
        """Проставить `archived_at` всем строкам сессии. Возвращает кол-во строк."""
        return await asyncio.to_thread(
            self._mark_archived_sync, user_id, conversation_id
        )

    def _mark_archived_sync(self, user_id: int, conversation_id: str) -> int:
        conn = self._require_conn()
        try:
            cur = conn.execute(
                """
                UPDATE dialog_journal
                SET archived_at = ?
                WHERE user_id = ? AND conversation_id = ? AND archived_at IS NULL;
                """,
                (_now_iso(), int(user_id), str(conversation_id)),
            )
            conn.commit()
            return cur.rowcount
        except Exception:
            conn.rollback()
            raise

    # -- internals --------------------------------------------------------

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("DialogJournal.init() was not called")
        return self._conn
