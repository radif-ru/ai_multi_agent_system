"""Модуль безопасности приложения.

Содержит инструменты для защиты от prompt injection и других атак на LLM-системы.
"""

from app.security.file_id_mapper import (
    FileIdMapper,
    clear_global_mapper,
    get_global_mapper,
)
from app.security.input_sanitizer import sanitize_user_input
from app.security.response_sanitizer import sanitize_response

__all__ = [
    "FileIdMapper",
    "clear_global_mapper",
    "get_global_mapper",
    "sanitize_user_input",
    "sanitize_response",
]
