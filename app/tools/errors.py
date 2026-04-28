"""Исключения tool-слоя.

См. `_docs/tools.md` §2, §3.
"""

from __future__ import annotations


class ToolError(Exception):
    """Доменная ошибка tool'а: возвращается агенту как observation."""


class ToolNotFound(KeyError):
    """Запрошен tool, не зарегистрированный в `ToolRegistry`."""


class ArgsValidationError(ValueError):
    """Аргументы tool'а не прошли валидацию по `args_schema`."""
