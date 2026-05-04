"""Консольный адаптер для работы с агентом.

ConsoleAdapter — REPL-цикл, который читает ввод пользователя,
выполняет команды через общий модуль `app/commands/` и печатает
результат в stdout. См. `_docs/console-adapter.md`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.commands.context import CommandContext, CommandResult


class ConsoleAdapter:
    """Консольный адаптер для работы с агентом.

    Реализует REPL-цикл: читает строку → парсит команду/текст → вызывает
    общие команды или core.handle_user_task → печатает ответ.
    """

    def __init__(
        self,
        *,
        user_id: int = -1,
        chat_id: int = -1,
        settings: Any,
        user_settings: Any,
        prompts: Any,
        tools: Any,
        skills: Any,
        conversations: Any,
        archiver: Any,
        core_handle_user_task: Any,
    ) -> None:
        """Инициализировать консольный адаптер.

        Args:
            user_id: фиксированный user_id для консоли (default -1)
            chat_id: фиксированный chat_id для консоли (default -1)
            settings: конфигурация приложения
            user_settings: реестр настроек пользователя
            prompts: загрузчик промптов
            tools: реестр инструментов
            skills: реестр скиллов
            conversations: хранилище диалогов
            archiver: архиватор сессий
            core_handle_user_task: функция core.handle_user_task для текстовых сообщений
        """
        self.user_id = user_id
        self.chat_id = chat_id
        self.settings = settings
        self.user_settings = user_settings
        self.prompts = prompts
        self.tools = tools
        self.skills = skills
        self.conversations = conversations
        self.archiver = archiver
        self.core_handle_user_task = core_handle_user_task

        from app.commands import CommandRegistry

        self.command_registry = CommandRegistry()

    def _build_context(self) -> "CommandContext":
        """Построить контекст команды."""
        from app.commands.context import CommandContext

        return CommandContext(
            user_id=self.user_id,
            chat_id=self.chat_id,
            settings=self.settings,
            user_settings=self.user_settings,
            prompts=self.prompts,
            tools=self.tools,
            skills=self.skills,
            conversations=self.conversations,
            archiver=self.archiver,
        )

    async def run(self) -> None:
        """Запустить REPL-цикл консольного адаптера."""
        import readline

        print("Консольный режим AI-агента. Введите /help для справки, /exit для выхода.")

        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                # Ctrl+D
                print("\nВыход.")
                break
            except KeyboardInterrupt:
                # Ctrl+C
                print("\nПрервано. Введите /exit для выхода или продолжайте.")
                continue

            if not line:
                continue

            if line == "/exit":
                print("Выход.")
                break

            # Проверка команды
            if line.startswith("/"):
                await self._handle_command(line)
            else:
                await self._handle_text(line)

    async def _handle_command(self, line: str) -> None:
        """Обработать команду."""
        parts = line.split(maxsplit=1)
        command_name = parts[0][1:]  # убираем слеш
        args = parts[1] if len(parts) > 1 else ""

        ctx = self._build_context()

        try:
            # Для команды /new передаём callback для прогресса
            if command_name == "new":

                async def _progress_callback(text: str) -> None:
                    print(f"⏳ {text}")

                result = await self.command_registry.execute(
                    command_name, ctx, args=args, progress_callback=_progress_callback
                )
            else:
                result = await self.command_registry.execute(command_name, ctx, args=args)
            print(result.text)
        except Exception as exc:  # noqa: BLE001
            print(f"Ошибка: {exc}")

    async def _handle_text(self, text: str) -> None:
        """Обработать текстовое сообщение."""
        ctx = self._build_context()

        # Дописываем сообщение в историю
        self.conversations.add_user_message(self.user_id, text)

        try:
            response = await self.core_handle_user_task(
                text=text,
                user_id=self.user_id,
                chat_id=self.chat_id,
                conversations=self.conversations,
                model=self.user_settings.get_model(self.user_id),
                system_prompt=self.user_settings.get_prompt(self.user_id),
            )
            print(response)

            # Дописываем ответ ассистента в историю
            self.conversations.add_assistant_message(self.user_id, response)

            # Условная in-session суммаризация
            history = self.conversations.get_history(self.user_id)
            if len(history) >= self.settings.history_summary_threshold:
                from app.services.summarizer import Summarizer

                summarizer = Summarizer(llm=None)  # будет заполнен через DI
                # TODO: реализовать суммаризацию для консоли
        except Exception as exc:  # noqa: BLE001
            print(f"Ошибка: {exc}")
