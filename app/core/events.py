"""Событийная шина (EventBus) и базовый Event.

Минимальная реализация async pub/sub для событий приложения.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Callable

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from app.users.models import User

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Базовый класс для всех событий.

    Все события должны наследоваться от этого класса и определять
    `event_type: ClassVar[str]` для идентификации типа события.
    """

    event_type: ClassVar[str] = "base"


@dataclass
class UserCreated(Event):
    """Событие создания пользователя.

    Публикуется UserRepository при создании нового пользователя.
    """

    event_type: ClassVar[str] = "user_created"
    user: "User"


@dataclass
class MessageReceived(Event):
    """Событие получения сообщения от пользователя.

    Публикуется хендлером при входящем тексте или файле после получения user.
    """

    event_type: ClassVar[str] = "message_received"
    user: "User"
    text: str
    conversation_id: str
    channel: str


@dataclass
class ResponseGenerated(Event):
    """Событие генерации ответа от LLM.

    Публикуется хендлером после получения ответа от core.handle_user_task,
    перед отправкой пользователю.
    """

    event_type: ClassVar[str] = "response_generated"
    user: "User"
    text: str
    conversation_id: str
    channel: str


class EventBus:
    """In-memory событийная шина с async pub/sub.

    Поддерживает подписку на конкретные типы событий и публикацию.
    Подписчики вызываются последовательно в порядке регистрации (FIFO).
    Исключения в подписчиках логируются как WARNING и не прерывают
    других подписчиков или публикатора.
    """

    def __init__(self) -> None:
        """Инициализировать шину событий."""
        self._subscribers: dict[str, list[Callable[[Event], Awaitable[None]]]] = {}

    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """Подписаться на события указанного типа.

        Аргументы:
            event_type: класс события (должен быть подтипом Event).
            handler: асинхронный обработчик события.

        Raises:
            TypeError: если event_type не является подтипом Event.
        """
        if not issubclass(event_type, Event):
            raise TypeError(f"{event_type.__name__} не является подтипом Event")

        type_name = event_type.event_type
        if type_name not in self._subscribers:
            self._subscribers[type_name] = []
        self._subscribers[type_name].append(handler)
        handler_name = getattr(handler, '__name__', getattr(handler, 'func', lambda: None).__name__ if hasattr(handler, 'func') else str(handler))
        logger.info(
            "Подписчик зарегистрирован: event_type=%s, handler=%s",
            type_name,
            handler_name,
        )

    async def publish(self, event: Event) -> None:
        """Опубликовать событие.

        Вызывает всех подписчиков данного типа события в порядке регистрации.
        Исключения в подписчиках логируются как WARNING и не прерывают
        других подписчиков.

        Аргументы:
            event: экземпляр события для публикации.
        """
        event_type = event.event_type
        handlers = self._subscribers.get(event_type, [])

        logger.info(
            "Публикация события: event_type=%s, subscribers=%d",
            event_type,
            len(handlers),
        )

        for handler in handlers:
            try:
                await handler(event)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Ошибка в подписчике: event_type=%s, handler=%s",
                    event_type,
                    handler.__name__,
                    exc_info=True,
                )
