"""Глобальный error handler Telegram-адаптера.

См. `_docs/architecture.md` §7 (таблица обработки ошибок) и
`_docs/testing.md` §3.11.

Ловит **любое необработанное исключение** в handler'ах команд и текста,
пишет в лог и отвечает пользователю нейтральным сообщением. Polling от
этого не падает.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

GENERIC_ERROR_REPLY = "Что-то пошло не так. Попробуйте ещё раз."


def build_error_handler() -> Callable[[ErrorEvent], Awaitable[bool]]:
    """Собрать обработчик `aiogram.errors`-события."""

    async def on_error(event: ErrorEvent) -> bool:
        logger.error(
            "unhandled exception in handler: %s",
            event.exception,
            exc_info=event.exception,
        )
        message = event.update.message if event.update is not None else None
        if message is not None:
            try:
                await message.answer(GENERIC_ERROR_REPLY)
            except Exception:  # noqa: BLE001
                logger.exception("failed to send error reply to user")
        # True → исключение помечено как обработанное, polling продолжается.
        return True

    return on_error


def build_errors_router() -> Router:
    """Собрать aiogram-Router c глобальным error handler'ом."""
    router = Router(name="errors")
    router.errors.register(build_error_handler())
    return router
