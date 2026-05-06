"""Санитайзинг ответов модели для защиты от data leakage.

См. задачу 7.1 спринта 05.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Паттерны системной информации для маскирования
_SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Полные пути к файлам (Unix и Windows)
    (re.compile(r"[a-zA-Z]:\\[^<>:\"|?*\n]+"), "[FILE_PATH]"),  # Windows: C:\path\to\file
    (re.compile(r"/[^<>\s\"'|?*]+/[^<>\s\"'|?*]*"), "[FILE_PATH]"),  # Unix: /path/to/file
    # Конфигурационные ключи (типичные форматы)
    (re.compile(r"[A-Z_]{2,}=\s*[\"']?[^\s\"']+[\"']?"), "[CONFIG_KEY]"),  # KEY=value
    (re.compile(r"[a-z][a-z_]+\.[a-z_]+\s*="), "[CONFIG_KEY]"),  # config.key=
    # Фрагменты системного промпта (по ключевым словам)
    (re.compile(r"#\s*(Запреты|Правила безопасности|Готовность|Инструкции)", re.IGNORECASE), "[SYSTEM_SECTION]"),
    (re.compile(r"Ты\s+(—|есть)\s+(AI|агент|помощник)", re.IGNORECASE), "[SYSTEM_IDENTITY]"),
]


def _detect_sensitive(text: str) -> tuple[bool, list[str]]:
    """Детектировать чувствительную информацию в тексте.

    Args:
        text: Проверяемый текст.

    Returns:
        (is_sensitive, detected_patterns) — флаг наличия чувствительной
        информации и список названий обнаруженных паттернов.
    """
    detected: list[str] = []
    for pattern, pattern_name in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            detected.append(pattern_name)

    return len(detected) > 0, detected


def sanitize_response(text: str) -> str:
    """Санитайзинг ответов модели для защиты от data leakage.

    Детектирует чувствительную информацию (пути к файлам, конфигурационные
    ключи, фрагменты системного промпта) и маскирует её.

    Args:
        text: Ответ модели.

    Returns:
        Текст с замаскированной чувствительной информацией.
    """
    is_sensitive, detected = _detect_sensitive(text)

    if not is_sensitive:
        return text

    # Логируем обнаружение
    log_msg = f"Обнаружена чувствительная информация в ответе: {', '.join(set(detected))}"
    logger.warning(log_msg)

    # Маскируем обнаруженные паттерны
    sanitized = text
    for pattern, mask in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(mask, sanitized)

    logger.info("Ответ очищен от чувствительной информации")
    return sanitized
