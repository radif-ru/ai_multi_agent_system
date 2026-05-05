"""Подписчики событий для записи в ConversationStore.

Модуль содержит функции-подписчики, которые записывают сообщения
пользователя и ассистента в ConversationStore при публикации событий
MessageReceived и ResponseGenerated.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.events import MessageReceived, ResponseGenerated
    from app.services.conversation import ConversationStore

logger = logging.getLogger(__name__)


async def on_message_received(
    event: "MessageReceived",
    conversations: "ConversationStore",
) -> None:
    """Подписчик на событие MessageReceived - записывает сообщение пользователя.

    Аргументы:
        event: событие получения сообщения от пользователя
        conversations: хранилище диалогов
    """
    # Используем user.id как ключ для ConversationStore
    user_id = int(event.user.external_id) if event.user.external_id.isdigit() else event.user.external_id
    conversations.add_user_message(user_id, event.text)
    logger.debug(
        "Записано сообщение пользователя в ConversationStore: user_id=%s conversation_id=%s",
        user_id,
        event.conversation_id,
    )


async def on_response_generated(
    event: "ResponseGenerated",
    conversations: "ConversationStore",
) -> None:
    """Подписчик на событие ResponseGenerated - записывает ответ ассистента.

    Аргументы:
        event: событие генерации ответа от LLM
        conversations: хранилище диалогов
    """
    # Используем user.id как ключ для ConversationStore
    user_id = int(event.user.external_id) if event.user.external_id.isdigit() else event.user.external_id
    conversations.add_assistant_message(user_id, event.text)
    logger.debug(
        "Записан ответ ассистента в ConversationStore: user_id=%s conversation_id=%s",
        user_id,
        event.conversation_id,
    )
