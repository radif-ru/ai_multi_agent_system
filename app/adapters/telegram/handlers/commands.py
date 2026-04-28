"""Handler'ы команд Telegram-адаптера.

Покрытые команды: `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`.

См. `_docs/commands.md` (контракт), `_docs/architecture.md` §3.12 (адаптер
не знает про executor / tools напрямую — только про прослойки сервисов).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.archiver import Archiver
    from app.services.conversation import ConversationStore
    from app.services.model_registry import UserSettingsRegistry
    from app.services.prompts import PromptLoader

logger = logging.getLogger(__name__)

PROMPT_PREVIEW_CHARS = 200


_START_TEXT = (
    "Привет! Я — AI-агент на локальной LLM.\n"
    "\n"
    "Я не просто отвечаю — я решаю задачи: думаю, выбираю инструмент, "
    "смотрю результат и так до финального ответа.\n"
    "\n"
    "Команды:\n"
    "/help — подробная справка\n"
    "/models — список моделей\n"
    "/model <имя> — выбрать модель\n"
    "/prompt <текст> — задать системный промпт (без текста — сброс)\n"
    "/new — закрыть текущую сессию (с архивированием) и начать новую\n"
    "/reset — очистить контекст и сбросить настройки"
)


def build_command_handlers(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    prompts: "PromptLoader",
    tools: Any,
    skills: Any,
    conversations: "ConversationStore",
    archiver: "Archiver",
) -> dict[str, Any]:
    """Собрать словарь handler'ов команд.

    Возвращает `dict[command_name, async callable]`. Используется как
    `build_commands_router`, так и тестами (которые вызывают функции напрямую,
    минуя aiogram-диспетчеризацию).
    """

    async def cmd_start(message: Message) -> None:
        await message.answer(_START_TEXT)

    async def cmd_help(message: Message) -> None:
        user_id = _user_id(message)
        active_model = user_settings.get_model(user_id)

        prompt_override = user_settings.get_prompt(user_id)
        if prompt_override is None:
            prompt_text = prompts.agent_system_template
            prompt_origin = "по умолчанию"
        else:
            prompt_text = prompt_override
            prompt_origin = "пользовательский"
        prompt_preview = _truncate(prompt_text, PROMPT_PREVIEW_CHARS)

        tools_block = _format_descriptions(tools.list_descriptions())
        skills_block = _format_descriptions(skills.list_descriptions())

        text = (
            "Команды:\n"
            "/start — приветствие\n"
            "/help — эта справка\n"
            "/models — список моделей\n"
            "/model <имя> — выбрать модель\n"
            "/prompt <текст> — задать системный промпт (без текста — сброс)\n"
            "/new — архивировать сессию и начать новую\n"
            "/reset — очистить контекст и сбросить настройки\n"
            "\n"
            f"Текущая модель: {active_model}\n"
            f"Системный промпт ({prompt_origin}):\n{prompt_preview}\n"
            "\n"
            f"Доступные инструменты:\n{tools_block}\n"
            "\n"
            f"Доступные скиллы:\n{skills_block}"
        )
        await message.answer(text)

    async def cmd_models(message: Message) -> None:
        user_id = _user_id(message)
        active = user_settings.get_model(user_id)
        lines = ["Доступные модели:"]
        for name in settings.ollama_available_models:
            mark = " ← активная" if name == active else ""
            lines.append(f"• {name}{mark}")
        lines.append("")
        lines.append("Смени командой: /model <имя>")
        await message.answer("\n".join(lines))

    async def cmd_model(message: Message, command: CommandObject) -> None:
        user_id = _user_id(message)
        arg = (command.args or "").strip()
        if not arg:
            await message.answer("Использование: /model <имя>, список: /models")
            return
        if arg not in settings.ollama_available_models:
            available = ", ".join(settings.ollama_available_models)
            await message.answer(f"Модель не найдена. Доступно: {available}")
            return
        user_settings.set_model(user_id, arg)
        await message.answer(f"Модель переключена на {arg}.")

    async def cmd_prompt(message: Message, command: CommandObject) -> None:
        user_id = _user_id(message)
        arg = (command.args or "").strip()
        if not arg:
            user_settings.reset_prompt(user_id)
            await message.answer(
                "Системный промпт сброшен к значению по умолчанию."
            )
            return
        user_settings.set_prompt(user_id, arg)
        await message.answer("Системный промпт обновлён.")

    async def cmd_new(message: Message) -> None:
        user_id = _user_id(message)
        chat_id = message.chat.id if message.chat is not None else user_id
        history = conversations.get_history(user_id)
        if not history:
            conversations.rotate_conversation_id(user_id)
            await message.answer("Сессия пустая, новая открыта.")
            return
        conversation_id = conversations.current_conversation_id(user_id)
        try:
            inserted = await archiver.archive(
                history,
                conversation_id=conversation_id,
                user_id=user_id,
                chat_id=chat_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "/new archive failed user=%s conv=%s", user_id, conversation_id
            )
            await message.answer(
                f"Архивирование не удалось: {exc}. "
                "Сессия сохранена, попробуйте /new ещё раз позже."
            )
            return
        conversations.clear(user_id)
        conversations.rotate_conversation_id(user_id)
        await message.answer(
            f"Архивировано {inserted} чанков, новая сессия открыта."
        )

    async def cmd_reset(message: Message) -> None:
        user_id = _user_id(message)
        conversations.clear(user_id)
        user_settings.reset(user_id)
        conversations.rotate_conversation_id(user_id)
        await message.answer(
            "Контекст диалога очищен, модель и системный промпт "
            "сброшены к значениям по умолчанию."
        )

    return {
        "start": cmd_start,
        "help": cmd_help,
        "models": cmd_models,
        "model": cmd_model,
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
) -> Router:
    """Собрать aiogram-Router с handler'ами команд.

    Тонкая обёртка над `build_command_handlers`, которая регистрирует функции
    под нужными `Command(...)`-фильтрами. Зависимости передаются явно —
    это упрощает unit-тесты и даёт жизненный цикл «один экземпляр на
    приложение» (см. `_docs/instructions.md` §3).
    """

    handlers = build_command_handlers(
        settings=settings,
        user_settings=user_settings,
        prompts=prompts,
        tools=tools,
        skills=skills,
        conversations=conversations,
        archiver=archiver,
    )
    router = Router(name="commands")
    router.message.register(handlers["start"], Command("start"))
    router.message.register(handlers["help"], Command("help"))
    router.message.register(handlers["models"], Command("models"))
    router.message.register(handlers["model"], Command("model"))
    router.message.register(handlers["prompt"], Command("prompt"))
    router.message.register(handlers["new"], Command("new"))
    router.message.register(handlers["reset"], Command("reset"))
    return router


def _user_id(message: Message) -> int:
    """Достать user_id из сообщения; в Telegram он есть всегда для текстовых апдейтов."""

    if message.from_user is None:
        # Технически в полинге это не должно случаться для текстовых сообщений,
        # но контракт aiogram допускает None — лучше явный сбой, чем тихий 0.
        raise RuntimeError("message.from_user is None — невозможно определить user_id")
    return message.from_user.id


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _format_descriptions(descriptions: list[dict[str, Any]]) -> str:
    if not descriptions:
        return "(нет)"
    return "\n".join(
        f"• {d['name']} — {d.get('description', '')}".rstrip(" —")
        for d in descriptions
    )
