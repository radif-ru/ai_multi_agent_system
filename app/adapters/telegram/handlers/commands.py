"""Handler'ы команд Telegram-адаптера.

Покрытые команды: `/start`, `/help`, `/models`, `/model`, `/search_engines`,
`/search_engine`, `/prompt`, `/new`, `/reset`.

Логика команд вынесена в общий модуль `app/commands/` для переиспользования
в других адаптерах (консоль, web, MAX). Telegram-адаптер — тонкая обёртка,
которая вызывает общие команды и отправляет результат через `message.answer()`.

См. `_docs/commands.md` (контракт), `_docs/architecture.md` §3.12 (адаптер
не знает про executor / tools напрямую — только про прослойки сервисов),
`_docs/console-adapter.md` §8 (пример использования общих команд).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.commands import CommandContext, CommandRegistry

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.archiver import Archiver
    from app.services.conversation import ConversationStore
    from app.services.model_registry import UserSettingsRegistry
    from app.services.prompts import PromptLoader

logger = logging.getLogger(__name__)


def build_command_handlers(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    prompts: "PromptLoader",
    tools: Any,
    skills: Any,
    conversations: "ConversationStore",
    archiver: "Archiver",
    users: Any = None,
) -> dict[str, Any]:
    """Собрать словарь handler'ов команд.

    Возвращает `dict[command_name, async callable]`. Используется как
    `build_commands_router`, так и тестами (которые вызывают функции напрямую,
    минуя aiogram-диспетчеризацию).

    Логика команд вынесена в `app.commands.CommandRegistry`, здесь только
    Telegram-специфичная обёртка (получение user_id/chat_id, отправка ответа).
    """
    registry = CommandRegistry()

    async def cmd_start(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        result = await registry.execute("start", ctx)
        await message.answer(result.text)

    async def cmd_help(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        result = await registry.execute("help", ctx)
        await message.answer(result.text)

    async def cmd_models(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        result = await registry.execute("models", ctx)
        await message.answer(result.text)

    async def cmd_model(message: Message, command: CommandObject) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        arg = (command.args or "").strip()
        result = await registry.execute("model", ctx, args=arg)
        await message.answer(result.text)

    async def cmd_search_engines(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        result = await registry.execute("search_engines", ctx)
        await message.answer(result.text)

    async def cmd_search_engine(message: Message, command: CommandObject) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        arg = (command.args or "").strip()
        result = await registry.execute("search_engine", ctx, args=arg)
        await message.answer(result.text)

    async def cmd_prompt(message: Message, command: CommandObject) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        arg = (command.args or "").strip()
        result = await registry.execute("prompt", ctx, args=arg)
        await message.answer(result.text)

    async def cmd_new(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        # Получаем user для публикации события ConversationArchived
        user_obj = None
        if users is not None:
            user_obj, _ = await users.get_or_create(
                channel="telegram",
                external_id=str(user_id),
                display_name=message.from_user.full_name if message.from_user else None,
            )
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
            user=user_obj,
            channel="telegram",
        )

        # Показываем прогресс для долгих операций
        progress_msg = None
        last_update = 0.0

        async def _progress_callback(text: str) -> None:
            nonlocal progress_msg, last_update
            now = time.monotonic()
            # Обновляем не чаще чем раз в 3 секунды
            if now - last_update < 3.0 and progress_msg is not None:
                return
            if progress_msg is None:
                progress_msg = await message.answer(f"⏳ {text}")
            else:
                await progress_msg.edit_text(f"⏳ {text}")
            last_update = now

        result = await registry.execute("new", ctx, progress_callback=_progress_callback)

        # Удаляем сообщение о прогрессе, если было
        if progress_msg is not None:
            try:
                await progress_msg.delete()
            except Exception:  # noqa: BLE001
                pass  # Игнорируем ошибки удаления

        await message.answer(result.text)

    async def cmd_reset(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        ctx = _build_context(
            user_id=user_id,
            chat_id=chat_id,
            settings=settings,
            user_settings=user_settings,
            prompts=prompts,
            tools=tools,
            skills=skills,
            conversations=conversations,
            archiver=archiver,
            users=users,
        )
        result = await registry.execute("reset", ctx)
        await message.answer(result.text)

    return {
        "start": cmd_start,
        "help": cmd_help,
        "models": cmd_models,
        "model": cmd_model,
        "search_engines": cmd_search_engines,
        "search_engine": cmd_search_engine,
        "prompt": cmd_prompt,
        "new": cmd_new,
        "reset": cmd_reset,
    }


def build_commands_router(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    prompts: "PromptLoader",
    tools: Any,
    skills: Any,
    conversations: "ConversationStore",
    archiver: "Archiver",
    users: Any = None,
) -> Router:
    """Собрать aiogram-Router с handler'ами команд.

    Тонкая обёртка над `build_command_handlers`, которая регистрирует функции
    под нужными `Command(...)`-фильтрами. Зависимости передаются явно —
    это упрощает unit-тесты и даёт жизненный цикл «один экземпляр на
    приложение» (см. `_docs/instructions.md` §4).
    """

    handlers = build_command_handlers(
        settings=settings,
        user_settings=user_settings,
        prompts=prompts,
        tools=tools,
        skills=skills,
        conversations=conversations,
        archiver=archiver,
        users=users,
    )
    router = Router(name="commands")
    router.message.register(handlers["start"], Command("start"))
    router.message.register(handlers["help"], Command("help"))
    router.message.register(handlers["models"], Command("models"))
    router.message.register(handlers["model"], Command("model"))
    router.message.register(handlers["search_engines"], Command("search_engines"))
    router.message.register(handlers["search_engine"], Command("search_engine"))
    router.message.register(handlers["prompt"], Command("prompt"))
    router.message.register(handlers["new"], Command("new"))
    router.message.register(handlers["reset"], Command("reset"))
    return router


def _build_context(
    *,
    user_id: int,
    chat_id: int,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    prompts: "PromptLoader",
    tools: Any,
    skills: Any,
    conversations: "ConversationStore",
    archiver: "Archiver",
    users: Any = None,
    user: Any = None,
    channel: str = "telegram",
) -> CommandContext:
    """Построить контекст команды для Telegram."""
    return CommandContext(
        user_id=user_id,
        chat_id=chat_id,
        settings=settings,
        user_settings=user_settings,
        prompts=prompts,
        tools=tools,
        skills=skills,
        conversations=conversations,
        archiver=archiver,
        users=users,
        user=user,
        channel=channel,
    )


def _user_id(message: Message) -> int:
    """Достать user_id из сообщения; в Telegram он есть всегда для текстовых апдейтов."""

    if message.from_user is None:
        # Технически в полинге это не должно случаться для текстовых сообщений,
        # но контракт aiogram допускает None — лучше явный сбой, чем тихий 0.
        raise RuntimeError("message.from_user is None — невозможно определить user_id")
    return message.from_user.id
