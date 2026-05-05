"""Реестр команд для всех адаптеров.

Содержит реализации всех команд (/start, /help, /models, /model, /prompt, /new, /reset),
которые могут быть вызваны из любого адаптера (Telegram, консоль, web, MAX).

Каждая команда принимает CommandContext и возвращает CommandResult.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.commands.context import CommandContext, CommandResult

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
    "/search_engines — список поисковиков\n"
    "/search_engine <имя> — выбрать поисковик\n"
    "/prompt <текст> — задать системный промпт (без текста — сброс)\n"
    "/new — закрыть текущую сессию (с архивированием) и начать новую\n"
    "/reset — очистить контекст и сбросить настройки"
)


async def cmd_start(ctx: "CommandContext") -> "CommandResult":
    """Команда /start — приветствие."""
    from app.commands.context import CommandResult

    return CommandResult(text=_START_TEXT)


async def cmd_help(ctx: "CommandContext") -> "CommandResult":
    """Команда /help — подробная справка."""
    from app.commands.context import CommandResult

    active_model = ctx.user_settings.get_model(ctx.user_id)

    prompt_override = ctx.user_settings.get_prompt(ctx.user_id)
    if prompt_override is None:
        prompt_text = ctx.prompts.agent_system_template
        prompt_origin = "по умолчанию"
    else:
        prompt_text = prompt_override
        prompt_origin = "пользовательский"
    prompt_preview = _truncate(prompt_text, PROMPT_PREVIEW_CHARS)

    tools_block = _format_descriptions(ctx.tools.list_descriptions())
    skills_block = _format_descriptions(ctx.skills.list_descriptions())

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
    return CommandResult(text=text)


async def cmd_models(ctx: "CommandContext") -> "CommandResult":
    """Команда /models — список доступных моделей."""
    from app.commands.context import CommandResult

    active = ctx.user_settings.get_model(ctx.user_id)
    lines = ["Доступные модели:"]
    for name in ctx.settings.ollama_available_models:
        mark = " ← активная" if name == active else ""
        lines.append(f"• {name}{mark}")
    lines.append("")
    lines.append("Смени командой: /model <имя>")
    return CommandResult(text="\n".join(lines))


async def cmd_model(ctx: "CommandContext", arg: str) -> "CommandResult":
    """Команда /model <name> — переключить активную модель."""
    from app.commands.context import CommandResult

    if not arg:
        return CommandResult(text="Использование: /model <имя>, список: /models")
    if arg not in ctx.settings.ollama_available_models:
        available = ", ".join(ctx.settings.ollama_available_models)
        return CommandResult(text=f"Модель не найдена. Доступно: {available}")
    ctx.user_settings.set_model(ctx.user_id, arg)
    return CommandResult(text=f"Модель переключена на {arg}.")


async def cmd_prompt(ctx: "CommandContext", arg: str) -> "CommandResult":
    """Команда /prompt [<text>] — установить или сбросить системный промпт."""
    from app.commands.context import CommandResult

    if not arg:
        ctx.user_settings.reset_prompt(ctx.user_id)
        return CommandResult(text="Системный промпт сброшен к значению по умолчанию.")
    ctx.user_settings.set_prompt(ctx.user_id, arg)
    return CommandResult(text="Системный промпт обновлён.")


async def cmd_new(ctx: "CommandContext", progress_callback: Any | None = None) -> "CommandResult":
    """Команда /new — архивировать сессию и открыть новую."""
    from app.commands.context import CommandResult

    # Архивируем ПОЛНЫЙ лог сессии (см. _docs/memory.md §2.5):
    # in-session `replace_with_summary` мог разрушить get_history(),
    # но `_session_log` хранит исходный диалог целиком.
    history = ctx.conversations.get_session_log(ctx.user_id)
    if not history:
        ctx.conversations.rotate_conversation_id(ctx.user_id)
        return CommandResult(text="Сессия пустая, новая открыта.")
    conversation_id = ctx.conversations.current_conversation_id(ctx.user_id)

    # Если callback не передан, создаём заглушку (для консоли)
    if progress_callback is None:

        async def _noop_callback(text: str) -> None:
            pass

        progress_callback = _noop_callback

    try:
        inserted = await ctx.archiver.archive(
            history,
            conversation_id=conversation_id,
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
            progress_callback=progress_callback,
            user=ctx.user,
            channel=ctx.channel,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "/new archive failed user=%s conv=%s", ctx.user_id, conversation_id
        )
        return CommandResult(
            text=(
                f"Архивирование не удалось: {exc}. "
                "Сессия сохранена, попробуйте /new ещё раз позже."
            )
        )

    ctx.conversations.clear(ctx.user_id)
    ctx.conversations.rotate_conversation_id(ctx.user_id)

    # Cleanup изображений пользователя перед очисткой контекста
    _cleanup_user_images(
        ctx.settings.tmp_base_dir,
        ctx.conversations,
        ctx.user_id,
    )

    return CommandResult(text=f"Архивировано {inserted} чанков, новая сессия открыта.")


async def cmd_reset(ctx: "CommandContext") -> "CommandResult":
    """Команда /reset — очистить контекст и сбросить настройки."""
    from app.commands.context import CommandResult

    ctx.conversations.clear(ctx.user_id)
    ctx.user_settings.reset(ctx.user_id)
    ctx.conversations.rotate_conversation_id(ctx.user_id)
    return CommandResult(
        text=(
            "Контекст диалога очищен, модель, системный промпт и поисковик "
            "сброшены к значениям по умолчанию."
        )
    )


async def cmd_search_engines(ctx: "CommandContext") -> "CommandResult":
    """Команда /search_engines — список доступных поисковиков."""
    from app.commands.context import CommandResult

    active = ctx.user_settings.get_search_engine(ctx.user_id)
    lines = ["Доступные поисковики:"]
    for name in ctx.settings.search_engines_available:
        mark = " ← активный" if name == active else ""
        lines.append(f"• {name}{mark}")
    lines.append("")
    lines.append("Смени командой: /search_engine <имя>")
    return CommandResult(text="\n".join(lines))


async def cmd_search_engine(ctx: "CommandContext", arg: str) -> "CommandResult":
    """Команда /search_engine <name> — переключить активный поисковик."""
    from app.commands.context import CommandResult

    if not arg:
        return CommandResult(text="Использование: /search_engine <имя>, список: /search_engines")
    if arg not in ctx.settings.search_engines_available:
        available = ", ".join(ctx.settings.search_engines_available)
        return CommandResult(text=f"Поисковик не найден. Доступно: {available}")
    ctx.user_settings.set_search_engine(ctx.user_id, arg)
    return CommandResult(text=f"Поисковик переключён на {arg}.")


class CommandRegistry:
    """Реестр команд для выполнения из любого адаптера."""

    def __init__(self) -> None:
        self._commands: dict[str, Any] = {
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

    async def execute(
        self,
        command_name: str,
        ctx: "CommandContext",
        args: str = "",
        progress_callback: Any | None = None,
    ) -> "CommandResult":
        """Выполнить команду.

        Args:
            command_name: имя команды (без слеша, например "start")
            ctx: контекст команды
            args: аргументы команды (для /model, /prompt)
            progress_callback: callback для прогресса (для /new)

        Returns:
            CommandResult с текстом ответа и флагами
        """
        from app.commands.context import CommandResult

        if command_name not in self._commands:
            return CommandResult(text=f"Неизвестная команда: {command_name}")

        cmd_func = self._commands[command_name]

        # Команды с аргументами
        if command_name in ("model", "prompt", "search_engine"):
            return await cmd_func(ctx, args)
        # Команда /new с progress_callback
        if command_name == "new":
            return await cmd_new(ctx, progress_callback=progress_callback)
        # Команды без аргументов
        return await cmd_func(ctx)

    def list_commands(self) -> list[str]:
        """Список доступных команд."""
        return list(self._commands.keys())


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


def _cleanup_user_images(
    tmp_dir: str,
    conversations: "ConversationStore",
    user_id: int,
) -> None:
    """Удалить каталог пользователя из tmp/.

    Удаляет весь каталог пользователя со всеми файлами.
    Используется при /new для очистки временных файлов пользователя.
    """
    tmp_path = Path(tmp_dir) / str(user_id)
    if not tmp_path.exists():
        return

    try:
        # Удаляем весь каталог пользователя
        import shutil

        shutil.rmtree(tmp_path)
        logger.info("cleanup: удалён каталог пользователя %s", tmp_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cleanup: не удалось удалить %s: %s", tmp_path, exc)
