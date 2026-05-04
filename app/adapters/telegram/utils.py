"""Утилиты форматирования для Telegram-адаптера."""

from __future__ import annotations

import re
from html import escape as html_escape
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

    # Разбиваем текст на части по кодовым блокам
    parts = []
    last_end = 0
    for match in code_blocks:
        start, end = match.span()
        # Текст до блока
        before = text[last_end:start]
        if before:
            parts.append(("text", before))
        # Кодовый блок
        lang = match.group(1) or "text"
        code = match.group(2)
        parts.append(("code", lang, code))
        last_end = end
    
    # Текст после последнего блока
    if last_end < len(text):
        parts.append(("text", text[last_end:]))
    
    # Формируем результат
    formatted_parts = []
    for part in parts:
        if part[0] == "text":
            # Экранируем текст
            formatted_parts.append(html_escape(part[1]))
        else:
            # Преобразуем кодовый блок в HTML
            lang = part[1]
            code = part[2]
            code_escaped = html_escape(code)
            formatted_parts.append(f'<pre><code class="language-{lang}">{code_escaped}</code></pre>')
    
    formatted = "".join(formatted_parts)
    return formatted, ParseMode.HTML
