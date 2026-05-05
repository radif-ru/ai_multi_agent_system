"""Модели пользователей."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    """Пользователь системы.

    Атрибуты:
        id: Внутренний автоинкрементный идентификатор.
        channel: Канал адаптера ("telegram" или "console").
        external_id: Внешний идентификатор в канале (telegram_id, имя пользователя в консоли).
        display_name: Отображаемое имя (опционально).
        created_at: Время создания пользователя.
    """

    id: int
    channel: str
    external_id: str
    display_name: str | None
    created_at: datetime
