"""Error tracking через GlitchTip / Sentry-совместимый бэкенд.

Интеграция off-by-default: при пустом `settings.sentry_dsn` функция
`setup_sentry` ничего не делает, никаких сетевых запросов и инициализации
`sentry_sdk` не происходит.

Hook `before_send` подмешивает `trace_id` и `user_id` из contextvars
(`app.utils.tracing`) в событие — в `tags` и в `user.id`.

См. `_docs/observability.md` §5.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.utils.tracing import get_trace_id, get_user_id

logger = logging.getLogger(__name__)


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Обогатить событие `trace_id` и `user_id` из текущего контекста.

    Выполняется Sentry SDK на каждое отправляемое событие. Возврат `None`
    отменяет отправку — мы этого не делаем, только обогащаем.
    """
    trace_id = get_trace_id()
    user_id = get_user_id()

    if trace_id is not None:
        tags = event.setdefault("tags", {})
        # tags может быть list[tuple] в некоторых конфигурациях — в Sentry SDK 2.x по умолчанию dict.
        if isinstance(tags, dict):
            tags.setdefault("trace_id", trace_id)
        extra = event.setdefault("extra", {})
        if isinstance(extra, dict):
            extra.setdefault("trace_id", trace_id)

    if user_id is not None:
        user = event.setdefault("user", {})
        if isinstance(user, dict):
            user.setdefault("id", str(user_id))

    return event


def setup_sentry(settings: Settings) -> bool:
    """Инициализировать `sentry_sdk`, если задан `SENTRY_DSN`.

    Возвращает `True`, если инициализация выполнена, иначе `False`.
    При любой ошибке инициализации логируется и возвращается `False` —
    работа приложения не должна зависеть от наличия error tracking.
    """
    dsn = settings.sentry_dsn
    if not dsn:
        logger.debug("sentry: DSN не задан, error tracking выключен")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning("sentry: sentry-sdk не установлен, error tracking выключен")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
            before_send=_before_send,
            integrations=[
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("sentry: инициализация не удалась: %s", exc)
        return False

    logger.info(
        "sentry: инициализирован",
        extra={"service": "sentry", "environment": settings.sentry_environment},
    )
    return True


__all__ = ["setup_sentry", "_before_send"]
