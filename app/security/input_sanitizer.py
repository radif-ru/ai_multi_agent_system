"""Санитайзинг пользовательского ввода для защиты от prompt injection.

См. задачу 3.1 спринта 05.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

# Паттерны prompt injection для детекции
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "ignore all previous instructions" / "ignore previous instructions"
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE), "ignore_previous"),
    # "repeat your system prompt" / "print your instructions"
    (re.compile(r"(repeat|print)\s+(your\s+)?(system\s+prompt|instructions)", re.IGNORECASE), "repeat_prompt"),
    # "forget everything above" / "disregard all above"
    (re.compile(r"(forget|disregard)\s+(everything|all)\s+(above|previous)", re.IGNORECASE), "forget_all"),
    # "system:" / "SYSTEM:" в начале строки
    (re.compile(r"^system:", re.IGNORECASE), "system_prefix"),
    # "<|" / "|>" (разделители сообщений)
    (re.compile(r"<\||\|>", re.IGNORECASE), "message_separator"),
]


def _detect_injection(text: str) -> tuple[bool, list[str]]:
    """Детектировать паттерны prompt injection в тексте.

    Args:
        text: Проверяемый текст.

    Returns:
        (is_injection, detected_patterns) — флаг наличия инъекции и список
        названий обнаруженных паттернов.
    """
    detected: list[str] = []
    for pattern, pattern_name in _INJECTION_PATTERNS:
        if pattern.search(text):
            detected.append(pattern_name)

    return len(detected) > 0, detected


def sanitize_user_input(
    text: str,
    user_id: str | int | None = None,
    mode: Literal["log", "filter", "warn"] = "warn",
) -> str:
    """Санитайзинг пользовательского ввода для защиты от prompt injection.

    Детектирует подозрительные паттерны (prompt injection, попытки получить
    системный промпт и т.д.) и в зависимости от режима либо логирует,
    либо фильтрует, либо возвращает исходный текст с предупреждением.

    Args:
        text: Пользовательский ввод.
        user_id: Идентификатор пользователя для логирования.
        mode: Режим обработки:
            - "log": только логировать WARNING, текст возвращать как есть
            - "filter": удалить подозрительные паттерны из текста
            - "warn": вернуть исходный текст с префиксом-предупреждением

    Returns:
        Очищенный или исходный текст в зависимости от режима.
    """
    is_injection, detected = _detect_injection(text)

    if not is_injection:
        return text

    # Логируем обнаружение
    log_msg = f"Обнаружены паттерны prompt injection: {', '.join(detected)}"
    if user_id is not None:
        log_msg += f" (user_id={user_id})"
    logger.warning(log_msg)

    if mode == "log":
        # Только логируем, текст возвращаем как есть
        return text
    elif mode == "filter":
        # Удаляем подозрительные паттерны
        sanitized = text
        for pattern, _ in _INJECTION_PATTERNS:
            sanitized = pattern.sub("[ОБНАРУЖЕН И УДАЛЁН]", sanitized)
        logger.info("Текст очищен от паттернов prompt injection")
        return sanitized
    elif mode == "warn":
        # Возвращаем исходный текст с предупреждением
        return f"[⚠️ Обнаружены подозрительные паттерны: {', '.join(detected)}]\n\n{text}"
    else:
        # Неверный режим - возвращаем как есть
        logger.warning("Неверный режим санитайзинга: %s", mode)
        return text
