"""In-memory репозиторий пользователей."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.users.models import User

if TYPE_CHECKING:
    from app.core.events import EventBus

logger = logging.getLogger(__name__)


class UserRepository:
    """In-memory репозиторий пользователей.

    Единственная точка «получить или создать» пользователя по внешнему ключу.
    Потокобезопасность обеспечивается asyncio.Lock на запись.

    Атрибуты:
        _users: Словарь internal_id -> User.
        _by_external: Словарь (channel, external_id) -> internal_id.
        _next_id: Следующий автоинкрементный id.
        _lock: Lock для потокобезопасности записи.
    """

    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._by_external: dict[tuple[str, str], int] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        channel: str,
        external_id: str,
        display_name: str | None = None,
    ) -> tuple[User, bool]:
        """Получить или создать пользователя по внешнему ключу.

        Аргументы:
            channel: Канал адаптера ("telegram" или "console").
            external_id: Внешний идентификатор.
            display_name: Отображаемое имя (опционально).

        Возвращает:
            Кортеж (user, created), где created=True, если пользователь создан.
        """
        key = (channel, external_id)

        async with self._lock:
            if key in self._by_external:
                user_id = self._by_external[key]
                user = self._users[user_id]
                return user, False

            # Создаём нового пользователя
            user = User(
                id=self._next_id,
                channel=channel,
                external_id=external_id,
                display_name=display_name,
                created_at=datetime.now(),
            )
            self._users[user.id] = user
            self._by_external[key] = user.id
            self._next_id += 1

            logger.info(
                "Создан новый пользователь: id=%d channel=%s external_id=%s",
                user.id,
                channel,
                external_id,
            )

            return user, True

    async def get(self, user_id: int) -> User | None:
        """Получить пользователя по внутреннему id.

        Аргументы:
            user_id: Внутренний идентификатор пользователя.

        Возвращает:
            User или None, если пользователь не найден.
        """
        return self._users.get(user_id)

    async def get_by_external(self, channel: str, external_id: str) -> User | None:
        """Получить пользователя по внешнему ключу.

        Аргументы:
            channel: Канал адаптера.
            external_id: Внешний идентификатор.

        Возвращает:
            User или None, если пользователь не найден.
        """
        key = (channel, external_id)
        user_id = self._by_external.get(key)
        if user_id is None:
            return None
        return self._users.get(user_id)
