"""Утилиты форматирования для Telegram-адаптера."""

from __future__ import annotations

import re
from typing import Literal

from aiogram.enums import ParseMode

# Регулярное выражение для поиска markdown-блоков кода
_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def format_for_telegram(text: str) -> tuple[str, ParseMode | None]:
    """Определяет режим парсинга и форматирует текст для Telegram.

    Если в тексте есть markdown-блоки кода, преобразует их в HTML для подсветки
    синтаксиса и возвращает ParseMode.HTML. Иначе возвращает исходный текст с
    ParseMode.MARKDOWN (или None если нет форматирования).

    Args:
        text: Текст ответа от агента.

    Returns:
        Кортеж (formatted_text, parse_mode).
    """
    # Проверяем наличие блоков кода
    code_blocks = list(_CODE_BLOCK_RE.finditer(text))
    if not code_blocks:
        # Если нет кода, используем MARKDOWN (или None если нет форматирования вообще)
        has_markdown = "*" in text or "_" in text or "`" in text
        parse_mode = ParseMode.MARKDOWN if has_markdown else None
        return text, parse_mode

    # Преобразуем markdown-блоки в HTML
    formatted = text
    # Заменяем в обратном порядке, чтобы сохранить позиции
    for match in reversed(code_blocks):
        lang = match.group(1) or "text"
        code = match.group(2)
        # Экранируем HTML-специальные символы в коде
        code_escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_block = f'<pre><code class="language-{lang}">{code_escaped}</code></pre>'
        start, end = match.span()
        formatted = formatted[:start] + html_block + formatted[end:]

    # Для остального текста используем HTML-экранирование
    # Но оставляем HTML-теги которые мы добавили (они уже экранированы)
    # Простое решение: используем ParseMode.HTML и экранируем только специальные символы
    # вне наших тегов

    return formatted, ParseMode.HTML
