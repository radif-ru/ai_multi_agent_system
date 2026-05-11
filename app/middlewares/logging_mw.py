"""LoggingMiddleware — INFO-строка на каждый Telegram-апдейт.

См. `_docs/architecture.md` §3.12 и §9, `_docs/observability.md` §2.

Формат строки:

    update user=<id> chat=<id> type=<update-type> dur_ms=<n> status=ok|error

Каждому апдейту middleware присваивает свежий `trace_id` и биндит его
вместе с `user_id` в contextvars (см. `app.utils.tracing`) — это
прокидывается дальше во все логи, вызываемые внутри обработчика.
Если handler упал — статус `error`, исключение пробрасывается дальше
(глобальный error handler ловит и отвечает пользователю).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.utils.tracing import (
    bind_trace_id,
    bind_user_id,
    new_trace_id,
    reset_trace_id,
    reset_user_id,
)

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Логирует каждое событие aiogram (INFO) c длительностью и статусом.

    Попутно генерирует `trace_id` и биндит `user_id` в contextvars на
    время обработки апдейта, чтобы все вложенные логи несли один и тот
    же идентификатор.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started = time.monotonic()
        status = "ok"
        user_id, chat_id = _extract_ids(event)
        trace_token = bind_trace_id(new_trace_id())
        user_token = bind_user_id(user_id)
        try:
            return await handler(event, data)
        except Exception:
            status = "error"
            raise
        finally:
            dur_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "update user=%s chat=%s type=%s dur_ms=%d status=%s",
                user_id,
                chat_id,
                type(event).__name__,
                dur_ms,
                status,
            )
            reset_user_id(user_token)
            reset_trace_id(trace_token)


def _extract_ids(event: TelegramObject) -> tuple[Any, Any]:
    user = getattr(event, "from_user", None)
    user_id = getattr(user, "id", None) if user is not None else None
    chat = getattr(event, "chat", None)
    chat_id = getattr(chat, "id", None) if chat is not None else None
    if user_id is None and isinstance(event, Message) and event.from_user is not None:
        user_id = event.from_user.id
    return user_id, chat_id
