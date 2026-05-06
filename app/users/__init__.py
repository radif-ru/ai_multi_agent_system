"""Модуль пользователей.

Экспортирует User и UserRepository для идентификации пользователей
в адаптерах (Telegram, консоль) и для будущих событий.
"""

from app.users.models import User
from app.users.repository import UserRepository

__all__ = ["User", "UserRepository"]
