"""Модуль безопасности приложения.

Содержит инструменты для защиты от prompt injection и других атак на LLM-системы.
"""

from app.security.input_sanitizer import sanitize_user_input

__all__ = ["sanitize_user_input"]
