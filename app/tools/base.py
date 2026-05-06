"""Контракт tool'а и общие константы.

См. `_docs/tools.md` §2.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

TRUNCATION_SUFFIX: str = "... [truncated]"


class ToolContext(Protocol):
    """Зависимости, доступные tool'у в момент выполнения.

    Реальная реализация — собирается в `Executor`/`Core` (см. Этап 5–6
    спринта); в тестах подменяется простым объектом / `MagicMock`.
    """

    user_id: int
    chat_id: int
    conversation_id: str
    settings: Any
    llm: Any
    semantic_memory: Any
    skills: Any


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    args_schema: Mapping[str, Any]

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str: ...


def truncate_output(text: str, limit: int = 50000) -> str:
    """Усечение строки до `limit` символов с маркером."""

    if len(text) <= limit:
        return text
    head = text[: max(0, limit - len(TRUNCATION_SUFFIX))]
    return head + TRUNCATION_SUFFIX
