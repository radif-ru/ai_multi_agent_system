"""Консольный адаптер для работы с агентом.

ConsoleAdapter — REPL-цикл, который читает ввод пользователя,
выполняет команды через общий модуль `app/commands/` и печатает
результат в stdout. См. `_docs/console-adapter.md`.
"""

from __future__ import annotations

import inspect
import re
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.commands.context import CommandContext, CommandResult


# ANSI-цвета для консольного вывода
class Colors:
    """ANSI-цвета для консольного вывода."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    GRAY = "\033[90m"
    RED = "\033[91m"


def format_console_output(text: str) -> str:
    """Форматировать текст для консольного вывода с цветами.

    - Кодовые блоки выделяются синим цветом
    - Заголовки (начинающиеся с #) выделяются зелёным и жирным
    - Списки выделяются серым цветом
    """
    lines = text.split("\n")
    formatted_lines = []
    in_code_block = False
    code_lang = None

    for line in lines:
        # Проверка начала/конца кодового блока
        code_match = re.match(r"^```(\w*)$", line)
        if code_match:
            if not in_code_block:
                in_code_block = True
                code_lang = code_match.group(1) or "code"
                formatted_lines.append(f"{Colors.BLUE}{Colors.BOLD}--- {code_lang} ---{Colors.RESET}")
            else:
                in_code_block = False
                code_lang = None
                formatted_lines.append(f"{Colors.BLUE}{Colors.BOLD}--- end ---{Colors.RESET}")
            continue

        if in_code_block:
            # Код внутри блока - синий цвет
            formatted_lines.append(f"{Colors.BLUE}{line}{Colors.RESET}")
        elif line.startswith("#"):
            # Заголовки - зелёный жирный
            formatted_lines.append(f"{Colors.GREEN}{Colors.BOLD}{line}{Colors.RESET}")
        elif line.startswith(("-", "*", "+")) or re.match(r"^\d+\.", line):
            # Списки - серый цвет
            formatted_lines.append(f"{Colors.GRAY}{line}{Colors.RESET}")
        else:
            # Обычный текст - без форматирования
            formatted_lines.append(line)

    return "\n".join(formatted_lines)


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
        users: Any,
        event_bus: Any = None,
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
            users: репозиторий пользователей
            event_bus: событийная шина
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
        self.users = users
        self.event_bus = event_bus

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
            users=self.users,
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
                    print(f"{Colors.YELLOW}⏳ {text}{Colors.RESET}")

                result = await self.command_registry.execute(
                    command_name, ctx, args=args, progress_callback=_progress_callback
                )
            else:
                result = await self.command_registry.execute(command_name, ctx, args=args)
            print(format_console_output(result.text))
        except Exception as exc:  # noqa: BLE001
            print(f"{Colors.RED}Ошибка: {exc}{Colors.RESET}")

    async def _handle_text(self, text: str) -> None:
        """Обработать текстовое сообщение."""
        # Получаем или создаём пользователя
        user = None
        if hasattr(self.users, "get_or_create") and inspect.iscoroutinefunction(self.users.get_or_create):
            user, _ = await self.users.get_or_create("console", str(self.user_id), "Console User")
        ctx = self._build_context()

        # Публикуем MessageReceived
        if self.event_bus and user:
            from app.core.events import MessageReceived
            await self.event_bus.publish(MessageReceived(
                user=user,
                text=text,
                conversation_id=str(self.chat_id),
                channel="console"
            ))

        try:
            response = await self.core_handle_user_task(
                text=text,
                user_id=self.user_id,
                chat_id=self.chat_id,
                conversations=self.conversations,
                model=self.user_settings.get_model(self.user_id),
                system_prompt=self.user_settings.get_prompt(self.user_id),
            )

            # Публикуем ResponseGenerated
            if self.event_bus and user:
                from app.core.events import ResponseGenerated
                await self.event_bus.publish(ResponseGenerated(
                    user=user,
                    text=response,
                    conversation_id=str(self.chat_id),
                    channel="console"
                ))

            print(format_console_output(response))

            # Условная in-session суммаризация
            history = self.conversations.get_history(self.user_id)
            if len(history) >= self.settings.history_summary_threshold:
                from app.services.summarizer import Summarizer

                summarizer = Summarizer(llm=None)  # будет заполнен через DI
                # TODO: реализовать суммаризацию для консоли
        except Exception as exc:  # noqa: BLE001
            # Выводим детали ошибки для отладки
            print(f"{Colors.RED}Ошибка: {exc}{Colors.RESET}")
            # Если это LLMBadResponse и ошибка парсинга JSON, попробуем извлечь final_answer
            if "LLMBadResponse" in str(type(exc)) and "invalid JSON" in str(exc):
                # Попробуем извлечь final_answer из последнего сообщения модели
                history = self.conversations.get_history(self.user_id)
                if history:
                    last_assistant = history[-1].get("content", "")
                    if '"final_answer"' in last_assistant:
                        # Извлекаем final_answer через regex
                        import re
                        match = re.search(r'"final_answer"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', last_assistant, re.DOTALL)
                        if match:
                            final_answer = match.group(1)
                            # Декодируем escape-последовательности
                            try:
                                import json
                                final_answer = json.loads(f'"{final_answer}"')
                                if isinstance(final_answer, str) and final_answer.strip():
                                    print(f"{Colors.YELLOW}Извлечён final_answer из повреждённого JSON:{Colors.RESET}")
                                    print(format_console_output(final_answer))
                                    self.conversations.add_assistant_message(self.user_id, final_answer)
                            except Exception:
                                pass
