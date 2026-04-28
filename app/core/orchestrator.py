"""Core / Orchestrator — единственная точка входа от любого адаптера.

См. `_docs/architecture.md` §3.10. В MVP — тонкая прослойка-функция, которая
читает `conversation_id` из `ConversationStore` и делегирует выполнение
`Executor`. В будущем (Этап 4 roadmap) сюда добавится `Planner`/`Critic`,
адаптеры менять не понадобится — это и есть точка изоляции NFR-10/11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.executor import Executor
    from app.services.conversation import ConversationStore


async def handle_user_task(
    text: str,
    *,
    user_id: int,
    chat_id: int,
    conversations: "ConversationStore",
    executor: "Executor",
    model: str | None = None,
) -> str:
    """Запустить агентный цикл и вернуть финальный текст для пользователя.

    Args:
        text: формулировка задачи пользователя.
        user_id: Telegram user_id (или эквивалент в другом адаптере).
        chat_id: Telegram chat_id.
        conversations: in-memory история диалога (источник `conversation_id`).
        executor: настроенный экземпляр `Executor`.
        model: per-user override модели; `None` → default из `Settings`.
    """

    conversation_id = conversations.current_conversation_id(user_id)
    history = conversations.get_history(user_id)
    return await executor.run(
        goal=text,
        user_id=user_id,
        chat_id=chat_id,
        conversation_id=conversation_id,
        model=model,
        history=history,
    )
