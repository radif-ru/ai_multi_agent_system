"""Маскирование чувствительных значений в структурах для логов.

Используется в `extra=`-полях JSON-логов (см. `_docs/observability.md` §3),
чтобы не утекали токены, API-ключи и заголовок `Authorization`.

Правила:

- По умолчанию маскируются ключи, содержащие подстроки `token`, `key`,
  `secret`, `password`, `api_key`, а также любые варианты регистра
  заголовка `Authorization` (в том числе внутри вложенных словарей
  `headers`).
- Значения заменяются строкой `"***"`. Типы не сохраняются —
  маскирование предназначено для логов, а не для дальнейшей логики.
- Функция рекурсивно обходит словари и списки. Посторонние типы
  возвращаются как есть.
"""

from __future__ import annotations

from typing import Any

MASK = "***"

# Подстроки, при вхождении которых ключ считается секретным
# (проверка регистронезависимая).
_SECRET_KEY_PARTS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
)

# Отдельный список точных имён ключей (регистронезависимо), которые
# всегда маскируются, даже если не содержат подстрок выше. `"key"` сам
# по себе слишком общий (public_key, rsa_key и т.п.), поэтому не кладём
# его в `_SECRET_KEY_PARTS`, но явно перечисляем тут.
_SECRET_KEY_EXACT: frozenset[str] = frozenset({
    "key",
    "auth",
    "bearer",
    "x-api-key",
})


def _is_secret_key(key: str) -> bool:
    low = key.lower().strip()
    if low in _SECRET_KEY_EXACT:
        return True
    return any(part in low for part in _SECRET_KEY_PARTS)


def mask_secrets(value: Any) -> Any:
    """Вернуть копию `value` с замаскированными секретами.

    Для словарей: ключи, помеченные как секретные, получают значение
    `"***"`; остальные значения рекурсивно обрабатываются.
    Для списков/кортежей: рекурсивно обрабатываются элементы (контейнер
    возвращается как список).
    Остальные типы возвращаются как есть.
    """
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_secret_key(k):
                out[k] = MASK
            else:
                out[k] = mask_secrets(v)
        return out
    if isinstance(value, (list, tuple)):
        return [mask_secrets(v) for v in value]
    return value
