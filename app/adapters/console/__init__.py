"""Консольный адаптер для работы с агентом без Telegram.

Консольный адаптер — «эталонный» пример реализации адаптера,
который вызывает общие команды из `app/commands/` и печатает
результат в stdout. См. `_docs/console-adapter.md`.
"""

from app.adapters.console.adapter import ConsoleAdapter

__all__ = ["ConsoleAdapter"]
