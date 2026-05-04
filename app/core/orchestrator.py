"""Core / Orchestrator — единственная точка входа от любого адаптера.

См. `_docs/architecture.md` §3.10. В MVP — тонкая прослойка-функция, которая
читает `conversation_id` из `ConversationStore` и делегирует выполнение
`Executor`. В будущем (Этап 5 roadmap) сюда добавится `Planner`/`Critic`,
адаптеры менять не понадобится — это и есть точка изоляции NFR-10/11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.session_bootstrap import build_bootstrap_message

if TYPE_CHECKING:
    from app.agents.executor import Executor
    from app.config import Settings
    from app.services.conversation import ConversationStore
    from app.services.llm import OllamaClient
    from app.services.memory import SemanticMemory


async def handle_user_task(
    text: str,
    *,
    user_id: int,
    chat_id: int,
    conversations: "ConversationStore",
    executor: "Executor",
    model: str | None = None,
    settings: "Settings | None" = None,
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> str:
    """Запустить агентный цикл и вернуть финальный текст для пользователя.

    Args:
        text: формулировка задачи пользователя.
        user_id: Telegram user_id (или эквивалент в другом адаптере).
        chat_id: Telegram chat_id.
        conversations: in-memory история диалога (источник `conversation_id`).
        executor: настроенный экземпляр `Executor`.
        model: per-user override модели; `None` → default из `Settings`.
        settings: `Settings`; нужен для авто-подгрузки архива (см. `_docs/memory.md` §3.6).
        llm: `OllamaClient` — для embed запроса при авто-подгрузке.
        semantic_memory: `SemanticMemory` — для поиска по архиву.
    """

    conversation_id = conversations.current_conversation_id(user_id)
    history = conversations.get_history(user_id)
    if len(history) == 1 and settings is not None:
        bootstrap = await build_bootstrap_message(
            query=text,
            user_id=user_id,
            settings=settings,
            llm=llm,
            semantic_memory=semantic_memory,
        )
        if bootstrap is not None:
            history = [bootstrap, *history]
    return await executor.run(
        goal=text,
        user_id=user_id,
        chat_id=chat_id,
        conversation_id=conversation_id,
        model=model,
        history=history,
    )
