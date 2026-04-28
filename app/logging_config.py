"""Настройка логирования.

См. `_docs/stack.md` §8 и `_docs/architecture.md` §3.3.
"""

from __future__ import annotations

import logging
import logging.config

from app.config import Settings

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(settings: Settings) -> None:
    """Настроить root-логгер: консоль + RotatingFileHandler.

    Каталог под `settings.log_file` создаётся, если ещё не существует.
    """
    log_file = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": _FORMAT},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": settings.log_level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "level": settings.log_level,
                "filename": str(log_file),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["console", "file"],
        },
    }
    logging.config.dictConfig(config)
