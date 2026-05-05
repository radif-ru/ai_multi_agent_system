"""Подписчик событий для in-session суммаризации.

Модуль содержит функцию-подписчик, которая запускает суммаризацию
истории диалога при публикации события ResponseGenerated, если длина
истории превышает threshold.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.core.events import ResponseGenerated
    from app.services.conversation import ConversationStore
    from app.services.model_registry import UserSettingsRegistry
    from app.services.summarizer import Summarizer

logger = logging.getLogger(__name__)


async def on_response_generated_summarize(
    event: "ResponseGenerated",
    *,
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    user_settings: "UserSettingsRegistry",
    settings: "Settings",
) -> None:
    """Подписчик на событие ResponseGenerated - запускает in-session суммаризацию.

    Если длина истории диалога превышает history_summary_threshold, запускает
    суммаризацию истории и заменяет её на саммари с сохранением последних
    kept_tail сообщений.

    Аргументы:
        event: событие генерации ответа от LLM
        conversations: хранилище диалогов
        summarizer: суммаризатор
        user_settings: реестр настроек пользователя
        settings: конфигурация приложения
    """
    # Используем user.id как ключ для ConversationStore
    user_id = int(event.user.external_id) if event.user.external_id.isdigit() else event.user.external_id
    
    history = conversations.get_history(user_id)
    if len(history) < settings.history_summary_threshold:
        return
    
    try:
        model = user_settings.get_model(user_id)
        summary = await summarizer.summarize(history[:-2], model=model)
        conversations.replace_with_summary(user_id, summary, kept_tail=2)
        logger.info(
            "in-session суммаризация выполнена: user_id=%s conversation_id=%s history_len=%d",
            user_id,
            event.conversation_id,
            len(history),
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "in-session суммаризация не удалась: user_id=%s conversation_id=%s",
            user_id,
            event.conversation_id,
            exc_info=True,
        )
