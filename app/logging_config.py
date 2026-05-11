"""Настройка логирования.

Структурные JSON-логи с `trace_id` и `user_id` из contextvars
(см. `app.utils.tracing`). Каждая запись — одна валидная JSON-строка.

См. `_docs/stack.md` §8, `_docs/architecture.md` §3.3, `_docs/observability.md`.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import logging.config

from app.config import Settings
from app.utils.tracing import get_trace_id, get_user_id

SERVICE_NAME = "ai-multi-agent-system"

# Стандартные атрибуты `logging.LogRecord`, которые не считаем пользовательским
# `extra`-полем и не дублируем в JSON.
_RESERVED_LOGRECORD_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    # Наши собственные поля, выставляемые фильтром — их рендерим отдельно.
    "trace_id", "user_id",
}


class ContextFilter(logging.Filter):
    """Проставляет `trace_id`/`user_id` из contextvars в каждую запись."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        if not hasattr(record, "user_id"):
            record.user_id = get_user_id()
        return True


class JsonFormatter(logging.Formatter):
    """Форматтер, превращающий `LogRecord` в одну JSON-строку.

    Обязательные поля: `timestamp`, `level`, `service`, `name`, `message`,
    `trace_id`, `user_id`. Всё, что передано через `extra=` и не
    пересекается со служебными атрибутами `LogRecord`, кладётся в `extra`.
    """

    def __init__(self, *, service: str = SERVICE_NAME) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _dt.datetime.fromtimestamp(
                record.created, tz=_dt.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "name": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "user_id": getattr(record, "user_id", None),
        }

        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOGRECORD_ATTRS
            and not key.startswith("_")
        }
        if extra:
            payload["extra"] = extra

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = record.stack_info

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(settings: Settings, console_output: bool = True) -> None:
    """Настроить root-логгер: консоль + RotatingFileHandler.

    Оба handler'а пишут JSON через `JsonFormatter`; `ContextFilter`
    автоматически подмешивает `trace_id`/`user_id` из contextvars.

    Args:
        settings: конфигурация приложения.
        console_output: включить ли вывод логов в консоль (default True).
    """
    log_file = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handlers = ["file"]
    if console_output:
        handlers.append("console")

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": ContextFilter},
        },
        "formatters": {
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["context"],
                "level": settings.log_level_console,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "filters": ["context"],
                "level": settings.log_level_file,
                "filename": str(log_file),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": handlers,
        },
    }
    logging.config.dictConfig(config)
