"""Общий модуль команд для всех адаптеров (Telegram, консоль, web, MAX).

Команды вынесены из Telegram-специфичного кода в общий модуль для
переиспользования в других адаптерах. См. `_docs/console-adapter.md` §8.
"""

from app.commands.context import CommandContext, CommandResult
from app.commands.registry import CommandRegistry

__all__ = ["CommandContext", "CommandResult", "CommandRegistry"]
