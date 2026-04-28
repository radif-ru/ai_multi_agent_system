"""Handler произвольного текста: запуск агентного цикла.

См. `_docs/commands.md` § «Произвольный текст», `_docs/architecture.md` §4.

Поток:

1. Пустой/нетекстовый ввод → подсказка «В MVP я понимаю только текст».
2. Слишком длинный ввод (> `MAX_INPUT_LENGTH`) → подсказка, без обращения к LLM.
3. Сообщение пишется в `ConversationStore`, дальше вызывается
   `core.handle_user_task(...)` (адаптер не знает про executor напрямую).
4. Ошибки LLM-слоя превращаются в человекочитаемые ответы.
5. Ответ ассистента дописывается в `ConversationStore`.
6. При `len(history) >= history_summary_threshold` запускается in-session
   суммаризация; её падение — `WARNING`, ответ пользователю не страдает.
7. Длинный ответ (> 4096 символов) разбивается на несколько сообщений
   (Telegram-лимит).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from aiogram import Router
from aiogram.types import Message

from app.core.orchestrator import handle_user_task
from app.services.llm import LLMBadResponse, LLMTimeout, LLMUnavailable
from app.utils.text import split_long_message

if TYPE_CHECKING:
    from app.agents.executor import Executor
    from app.config import Settings
    from app.services.conversation import ConversationStore
    from app.services.llm import OllamaClient
    from app.services.memory import SemanticMemory
    from app.services.model_registry import UserSettingsRegistry
    from app.services.summarizer import Summarizer

logger = logging.getLogger(__name__)

MAX_INPUT_LENGTH = 4000
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

NON_TEXT_REPLY = "В MVP я понимаю только текст."
TOO_LONG_INPUT_REPLY = "Слишком длинный запрос, сократите формулировку."
LLM_UNAVAILABLE_REPLY = "LLM сейчас недоступна, попробуйте позже."
LLM_TIMEOUT_REPLY = "Модель слишком долго отвечает, попробуйте ещё раз."
LLM_BAD_RESPONSE_REPLY = (
    "Модель ответила в неожиданном формате, попробуйте ещё раз."
)
GENERIC_ERROR_REPLY = "Что-то пошло не так, попробуйте ещё раз."


def build_text_handler(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Callable[[Message], Awaitable[None]]:
    """Собрать async-handler для текстовых сообщений (без `/`-команд)."""

    async def handle_text(message: Message) -> None:
        text = message.text
        if not text:
            await message.answer(NON_TEXT_REPLY)
            return

        if message.from_user is None:
            # Технически возможно для каналов; в нашем MVP — игнорируем.
            return
        user_id = message.from_user.id
        chat_id = message.chat.id if message.chat is not None else user_id

        if len(text) > MAX_INPUT_LENGTH:
            await message.answer(TOO_LONG_INPUT_REPLY)
            return

        conversations.add_user_message(user_id, text)
        model = user_settings.get_model(user_id)

        try:
            reply = await handle_user_task(
                text,
                user_id=user_id,
                chat_id=chat_id,
                conversations=conversations,
                executor=executor,
                model=model,
                settings=settings,
                llm=llm,
                semantic_memory=semantic_memory,
            )
        except LLMTimeout:
            logger.warning("LLM timeout user=%s", user_id)
            await message.answer(LLM_TIMEOUT_REPLY)
            return
        except LLMUnavailable:
            logger.error("LLM unavailable user=%s", user_id)
            await message.answer(LLM_UNAVAILABLE_REPLY)
            return
        except LLMBadResponse:
            logger.warning("LLM bad response user=%s", user_id)
            await message.answer(LLM_BAD_RESPONSE_REPLY)
            return

        conversations.add_assistant_message(user_id, reply)

        history = conversations.get_history(user_id)
        if len(history) >= settings.history_summary_threshold:
            try:
                summary = await summarizer.summarize(
                    history[:-2], model=model
                )
                conversations.replace_with_summary(
                    user_id, summary, kept_tail=2
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "in-session summary failed user=%s",
                    user_id,
                    exc_info=True,
                )

        for part in split_long_message(reply, TELEGRAM_MAX_MESSAGE_LENGTH):
            await message.answer(part)

    return handle_text


def build_messages_router(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Router:
    """Собрать aiogram-Router для произвольных текстовых сообщений."""

    handler = build_text_handler(
        settings=settings,
        user_settings=user_settings,
        conversations=conversations,
        summarizer=summarizer,
        executor=executor,
        llm=llm,
        semantic_memory=semantic_memory,
    )
    router = Router(name="messages")
    router.message.register(handler)
    return router
