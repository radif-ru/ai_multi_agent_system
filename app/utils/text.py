"""Утилиты по работе с текстом.

Сейчас содержит только `split_long_message` — разбивку строки на части
не длиннее заданного лимита (Telegram-лимит 4096 символов на одно сообщение,
см. `_docs/current-state.md` §3 и `_docs/project-structure.md` § `app/utils/`).
"""

from __future__ import annotations


def split_long_message(text: str, limit: int) -> list[str]:
    """Разбить строку на части длиной не более `limit` символов.

    Алгоритм — простая фиксированная нарезка по индексу: предпочитаем
    предсказуемость и отсутствие потерь символов разбивке по словам.
    Пустая строка возвращается как `[""]`, чтобы вызывающий код мог
    единообразно итерироваться по результату.
    """

    if limit <= 0:
        raise ValueError("limit must be positive")
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]
