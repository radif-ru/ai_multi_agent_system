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
            "history": [],
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


async def test_orchestrator_passes_history(
    conversations: ConversationStore,
) -> None:
    """`handle_user_task` достаёт историю из стора и пробрасывает в Executor."""
    conversations.add_user_message(42, "Привет, я Радиф")
    conversations.add_assistant_message(42, "Привет, Радиф")
    conversations.add_user_message(42, "Как меня зовут?")
    executor = _FakeExecutor()

    await handle_user_task(
        "Как меня зовут?",
        user_id=42,
        chat_id=1,
        conversations=conversations,
        executor=executor,
    )

    assert executor.calls[0]["history"] == [
        {"role": "user", "content": "Привет, я Радиф"},
        {"role": "assistant", "content": "Привет, Радиф"},
        {"role": "user", "content": "Как меня зовут?"},
    ]


async def test_orchestrator_does_not_duplicate_goal(
    conversations: ConversationStore,
) -> None:
    """Последний user-message в `history` совпадает с `goal` — без дубля.

    Проверяется на уровне инварианта core: history передаётся целиком,
    дедупликация — обязанность `Executor.run` (см. `_docs/memory.md` §2.4).
    Здесь мы только убеждаемся, что core не модифицирует history.
    """
    conversations.add_user_message(7, "вопрос")
    executor = _FakeExecutor()

    await handle_user_task(
        "вопрос",
        user_id=7,
        chat_id=1,
        conversations=conversations,
        executor=executor,
    )

    history = executor.calls[0]["history"]
    assert history == [{"role": "user", "content": "вопрос"}]
    assert executor.calls[0]["goal"] == "вопрос"


class _FakeSettings:
    def __init__(self, *, enabled: bool = True, top_k: int = 3) -> None:
        self.embedding_model = "nomic-embed-text"
        self.session_bootstrap_enabled = enabled
        self.session_bootstrap_top_k = top_k


class _FakeLLM:
    def __init__(self, *, exc: Exception | None = None) -> None:
        self._exc = exc
        self.calls: list[Any] = []

    async def embed(self, text: str, *, model: str) -> list[float]:
        self.calls.append((text, model))
        if self._exc is not None:
            raise self._exc
        return [0.1, 0.2, 0.3]


class _FakeMemory:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []
        self.calls: list[Any] = []

    async def search(self, embedding: list[float], *, top_k: int, scope_user_id: int) -> list[dict[str, Any]]:
        self.calls.append((top_k, scope_user_id))
        return self._rows


async def test_bootstrap_prepends_system_when_first_turn(
    conversations: ConversationStore,
) -> None:
    """Первый ход новой сессии → перед history дописывается system из архива."""
    conversations.add_user_message(42, "Как меня зовут?")
    executor = _FakeExecutor()
    memory = _FakeMemory(rows=[{"text": "Пользователя зовут Радиф"}])

    await handle_user_task(
        "Как меня зовут?",
        user_id=42,
        chat_id=1,
        conversations=conversations,
        executor=executor,
        settings=_FakeSettings(),
        llm=_FakeLLM(),
        semantic_memory=memory,
    )

    history = executor.calls[0]["history"]
    assert len(history) == 2
    assert history[0]["role"] == "system"
    assert "Радиф" in history[0]["content"]
    assert history[1] == {"role": "user", "content": "Как меня зовут?"}
    assert memory.calls == [(3, 42)]


async def test_bootstrap_skipped_when_history_longer(
    conversations: ConversationStore,
) -> None:
    """Если в истории > 1 сообщения — авто-подгрузка не вызывается."""
    conversations.add_user_message(42, "Привет")
    conversations.add_assistant_message(42, "Привет")
    conversations.add_user_message(42, "Как меня зовут?")
    executor = _FakeExecutor()
    llm = _FakeLLM()
    memory = _FakeMemory(rows=[{"text": "x"}])

    await handle_user_task(
        "Как меня зовут?",
        user_id=42,
        chat_id=1,
        conversations=conversations,
        executor=executor,
        settings=_FakeSettings(),
        llm=llm,
        semantic_memory=memory,
    )

    assert llm.calls == []
    assert memory.calls == []
    assert all(m["role"] != "system" for m in executor.calls[0]["history"])


async def test_bootstrap_disabled_flag(
    conversations: ConversationStore,
) -> None:
    conversations.add_user_message(42, "q")
    executor = _FakeExecutor()
    llm = _FakeLLM()
    memory = _FakeMemory(rows=[{"text": "x"}])

    await handle_user_task(
        "q",
        user_id=42,
        chat_id=1,
        conversations=conversations,
        executor=executor,
        settings=_FakeSettings(enabled=False),
        llm=llm,
        semantic_memory=memory,
    )

    assert llm.calls == []
    assert memory.calls == []
    assert executor.calls[0]["history"] == [{"role": "user", "content": "q"}]


async def test_bootstrap_failure_does_not_break_flow(
    conversations: ConversationStore,
) -> None:
    """Падение embed → ход продолжается без авто-контекста."""
    conversations.add_user_message(42, "q")
    executor = _FakeExecutor()

    await handle_user_task(
        "q",
        user_id=42,
        chat_id=1,
        conversations=conversations,
        executor=executor,
        settings=_FakeSettings(),
        llm=_FakeLLM(exc=RuntimeError("ollama down")),
        semantic_memory=_FakeMemory(rows=[{"text": "x"}]),
    )

    assert executor.calls[0]["history"] == [{"role": "user", "content": "q"}]


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
