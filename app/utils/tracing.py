"""Контекст трассировки для структурных логов.

`trace_id` — короткий идентификатор, уникальный на одно внешнее действие
(Telegram update, команда консоли, фоновая таска). Привязывается к
текущему `asyncio.Task` через `contextvars.ContextVar`; логгинг-фильтр
(см. `app.logging_config`) автоматически прокидывает его в каждую
JSON-запись лога. `user_id` хранится тем же способом, чтобы подписчики
и сервисы не таскали его через все аргументы.

См. `_docs/observability.md`.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from typing import Any

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
user_id_var: ContextVar[Any] = ContextVar("user_id", default=None)


def new_trace_id() -> str:
    """Сгенерировать новый короткий `trace_id` (12 hex-символов)."""
    return uuid.uuid4().hex[:12]


def bind_trace_id(value: str | None) -> Token[str | None]:
    """Привязать `trace_id` к текущему контексту.

    Возвращает токен для последующего `reset_trace_id`.
    """
    return trace_id_var.set(value)


def get_trace_id() -> str | None:
    """Получить текущий `trace_id` из контекста (или `None`)."""
    return trace_id_var.get()


def reset_trace_id(token: Token[str | None]) -> None:
    """Сбросить `trace_id` по токену от `bind_trace_id`."""
    trace_id_var.reset(token)


def bind_user_id(value: Any) -> Token[Any]:
    """Привязать `user_id` к текущему контексту."""
    return user_id_var.set(value)


def get_user_id() -> Any:
    """Получить текущий `user_id` из контекста (или `None`)."""
    return user_id_var.get()


def reset_user_id(token: Token[Any]) -> None:
    """Сбросить `user_id` по токену от `bind_user_id`."""
    user_id_var.reset(token)
