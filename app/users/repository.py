"""SQLite-репозиторий пользователей.

Хранит таблицу `users` в той же `data/memory.db`, что и `SemanticMemory` /
`DialogJournal`. Соединение отдельное (как и у `DialogJournal`) — никаких
расширений не требуется. См. `_docs/memory.md` §5 и спринт 08, задача 2.1.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.users.models import User

if TYPE_CHECKING:
    from app.core.events import EventBus

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)


def _row_to_user(row: tuple) -> User:
    return User(
        id=int(row[0]),
        channel=str(row[1]),
        external_id=str(row[2]),
        display_name=row[3],
        created_at=_parse_iso(row[4]),
    )


class UserRepository:
    """SQLite-репозиторий пользователей.

    API синхронный по сути; внешние корутины оборачивают вызовы в
    `asyncio.to_thread`, как в `SemanticMemory`/`DialogJournal`. Запись
    `INSERT … ON CONFLICT … DO NOTHING RETURNING` атомарна на уровне SQLite,
    дополнительно асинхронный `Lock` сериализует конкурентные `get_or_create`
    в одном процессе, чтобы `UserCreated` публиковался ровно один раз на
    нового пользователя.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        event_bus: "EventBus | None" = None,
    ) -> None:
        self._db_path = db_path
        self._event_bus = event_bus
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle --------------------------------------------------------

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                channel      TEXT    NOT NULL,
                external_id  TEXT    NOT NULL,
                display_name TEXT,
                created_at   TEXT    NOT NULL,
                UNIQUE(channel, external_id)
            );
            """
        )
        conn.commit()
        self._conn = conn
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        logger.info("UserRepository: загружено пользователей в БД: %d", count)

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    # -- API --------------------------------------------------------------

    async def get_or_create(
        self,
        channel: str,
        external_id: str,
        display_name: str | None = None,
    ) -> tuple[User, bool]:
        """Получить или создать пользователя по внешнему ключу.

        Возвращает кортеж (user, created), где created=True, если строка была
        реально вставлена. `UserCreated` публикуется только при `created=True`.
        """
        async with self._lock:
            user, created = await asyncio.to_thread(
                self._get_or_create_sync, channel, external_id, display_name
            )
            if created:
                logger.info(
                    "Создан новый пользователь: id=%d channel=%s external_id=%s",
                    user.id, channel, external_id,
                )
                if self._event_bus is not None:
                    from app.core.events import UserCreated

                    await self._event_bus.publish(UserCreated(user=user))
            return user, created

    def _get_or_create_sync(
        self,
        channel: str,
        external_id: str,
        display_name: str | None,
    ) -> tuple[User, bool]:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT id, channel, external_id, display_name, created_at "
            "FROM users WHERE channel = ? AND external_id = ?",
            (channel, external_id),
        ).fetchone()
        if row is not None:
            return _row_to_user(row), False

        created_at = _now_iso()
        try:
            cur = conn.execute(
                "INSERT INTO users (channel, external_id, display_name, created_at) "
                "VALUES (?, ?, ?, ?)",
                (channel, external_id, display_name, created_at),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Гонка между процессами (другой инстанс успел вставить) —
            # перечитываем существующую строку.
            conn.rollback()
            row = conn.execute(
                "SELECT id, channel, external_id, display_name, created_at "
                "FROM users WHERE channel = ? AND external_id = ?",
                (channel, external_id),
            ).fetchone()
            assert row is not None
            return _row_to_user(row), False

        user = User(
            id=int(cur.lastrowid or 0),
            channel=channel,
            external_id=external_id,
            display_name=display_name,
            created_at=_parse_iso(created_at),
        )
        return user, True

    async def get(self, user_id: int) -> User | None:
        return await asyncio.to_thread(self._get_sync, user_id)

    def _get_sync(self, user_id: int) -> User | None:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT id, channel, external_id, display_name, created_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _row_to_user(row) if row is not None else None

    async def get_by_external(self, channel: str, external_id: str) -> User | None:
        return await asyncio.to_thread(
            self._get_by_external_sync, channel, external_id
        )

    def _get_by_external_sync(
        self, channel: str, external_id: str
    ) -> User | None:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT id, channel, external_id, display_name, created_at "
            "FROM users WHERE channel = ? AND external_id = ?",
            (channel, external_id),
        ).fetchone()
        return _row_to_user(row) if row is not None else None

    # -- internals --------------------------------------------------------

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("UserRepository.init() was not called")
        return self._conn
