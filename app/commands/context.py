"""Контекст и результат выполнения команды.

CommandContext содержит все зависимости, необходимые для выполнения команды.
CommandResult содержит текст ответа и опциональные флаги (например, clear_screen).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.archiver import Archiver
    from app.services.conversation import ConversationStore
    from app.services.model_registry import UserSettingsRegistry
    from app.services.prompts import PromptLoader
    from app.users.models import User
    from app.users.repository import UserRepository


@dataclass
class CommandContext:
    """Контекст выполнения команды.

    Содержит все зависимости, необходимые для выполнения команды:
    - user_id: идентификатор пользователя
    - chat_id: идентификатор чата (в Telegram может отличаться от user_id)
    - settings: конфигурация приложения
    - user_settings: реестр настроек пользователя
    - prompts: загрузчик промптов
    - tools: реестр инструментов
    - skills: реестр скиллов
    - conversations: хранилище диалогов
    - archiver: архиватор сессий
    - users: репозиторий пользователей (опционально для обратной совместимости с тестами)
    - user: объект пользователя (опционально, для публикации событий)
    - channel: канал адаптера ("telegram" или "console", опционально)
    """

    user_id: int
    chat_id: int
    settings: "Settings"
    user_settings: "UserSettingsRegistry"
    prompts: "PromptLoader"
    tools: Any
    skills: Any
    conversations: "ConversationStore"
    archiver: "Archiver"
    users: "UserRepository" = None
    user: "User | None" = None
    channel: str | None = None


@dataclass
class CommandResult:
    """Результат выполнения команды.

    text: текст ответа
    flags: опциональные флаги для адаптера (например, clear_screen для консоли)
    """

    text: str
    flags: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.flags is None:
            self.flags = {}
