"""Тесты `core.handle_user_task`.

См. `_docs/architecture.md` §3.10.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.orchestrator import handle_user_task
from app.services.conversation import ConversationStore


class _FakeExecutor:
    """Имитирует `Executor.run`, фиксируя переданные kwargs."""

    def __init__(self, reply: str = "финальный ответ") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.reply


@pytest.fixture
def conversations() -> ConversationStore:
    return ConversationStore(max_messages=10)


async def test_returns_executor_reply(conversations: ConversationStore) -> None:
    executor = _FakeExecutor("ок")
    reply = await handle_user_task(
        "привет",
        user_id=42,
        chat_id=777,
        conversations=conversations,
        executor=executor,
    )
    assert reply == "ок"


async def test_passes_conversation_id_from_store(
    conversations: ConversationStore,
) -> None:
    # Сначала закрепим conversation_id за пользователем.
    cid = conversations.current_conversation_id(42)
    executor = _FakeExecutor()

    await handle_user_task(
        "task",
        user_id=42,
        chat_id=777,
        conversations=conversations,
        executor=executor,
    )

    assert executor.calls == [
        {
            "goal": "task",
            "user_id": 42,
            "chat_id": 777,
            "conversation_id": cid,
            "model": None,
        }
    ]


async def test_creates_conversation_id_for_new_user(
    conversations: ConversationStore,
) -> None:
    executor = _FakeExecutor()
    await handle_user_task(
        "task",
        user_id=99,
        chat_id=1,
        conversations=conversations,
        executor=executor,
    )

    cid_after = conversations.current_conversation_id(99)
    assert executor.calls[0]["conversation_id"] == cid_after
    assert cid_after  # не пусто


async def test_forwards_model_override(conversations: ConversationStore) -> None:
    executor = _FakeExecutor()
    await handle_user_task(
        "task",
        user_id=1,
        chat_id=2,
        conversations=conversations,
        executor=executor,
        model="llama3:8b",
    )
    assert executor.calls[0]["model"] == "llama3:8b"
