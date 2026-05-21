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


# ---------------------------------------------------------------------------
# Multi-agent (Planner + Critic), см. _docs/multi-agent.md и спринт 07.
# ---------------------------------------------------------------------------


from app.agents.protocol import CriticVerdict, Plan, PlanStep  # noqa: E402


class _FakePlanner:
    def __init__(self, plan: Plan | None = None, *, exc: Exception | None = None) -> None:
        self._plan = plan or Plan(steps=(PlanStep(id=1, description="шаг 1"),))
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def plan(self, task: str, *, user_id: int, model: str | None = None) -> Plan:
        self.calls.append({"task": task, "user_id": user_id, "model": model})
        if self._exc is not None:
            raise self._exc
        return self._plan


class _FakeCritic:
    def __init__(self, verdicts: list[CriticVerdict]) -> None:
        # Очередь вердиктов; последний возвращается повторно при переборе.
        self._verdicts = list(verdicts)
        self.calls: list[dict[str, Any]] = []

    async def review(
        self, task: str, plan: Plan, draft: str, *, user_id: int, model: str | None = None
    ) -> CriticVerdict:
        self.calls.append({"task": task, "draft": draft, "plan_steps": len(plan.steps)})
        if len(self._verdicts) > 1:
            return self._verdicts.pop(0)
        return self._verdicts[0]


class _ReflSettings(_FakeSettings):
    def __init__(self, *, mode: str = "OFF", max_iter: int = 2) -> None:
        super().__init__(enabled=False)
        self.agent_reflection_mode = mode
        self.agent_reflection_max_iterations = max_iter


class _Registry:
    """Минимальный заменитель `UserSettingsRegistry.get_reflection_mode`."""

    def __init__(self, mode: str | None = None) -> None:
        self._mode = mode

    def get_reflection_mode(self, user_id: int) -> str | None:
        return self._mode


async def test_off_mode_skips_planner_and_critic(
    conversations: ConversationStore,
) -> None:
    executor = _FakeExecutor("ответ")
    planner = _FakePlanner()
    critic = _FakeCritic([CriticVerdict(verdict="PASS", feedback="")])

    reply = await handle_user_task(
        "задача",
        user_id=1,
        chat_id=2,
        conversations=conversations,
        executor=executor,
        settings=_ReflSettings(mode="OFF"),
        planner=planner,
        critic=critic,
    )

    assert reply == "ответ"
    assert planner.calls == []
    assert critic.calls == []
    assert len(executor.calls) == 1
    assert executor.calls[0]["goal"] == "задача"


async def test_off_when_planner_or_critic_missing(
    conversations: ConversationStore,
) -> None:
    """Без Planner/Critic режим NORMAL даунгрейдится в OFF."""
    executor = _FakeExecutor("ok")

    await handle_user_task(
        "t", user_id=1, chat_id=2,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="NORMAL"),
        planner=None, critic=None,
    )
    assert executor.calls[0]["goal"] == "t"


async def test_normal_pass_returns_first_draft(
    conversations: ConversationStore,
) -> None:
    executor = _FakeExecutor("draft-ok")
    plan = Plan(steps=(PlanStep(id=1, description="A"), PlanStep(id=2, description="B")))
    planner = _FakePlanner(plan)
    critic = _FakeCritic([CriticVerdict(verdict="PASS", feedback="")])

    reply = await handle_user_task(
        "сложная задача",
        user_id=1, chat_id=2,
        conversations=conversations,
        executor=executor,
        settings=_ReflSettings(mode="NORMAL"),
        planner=planner, critic=critic,
    )

    assert reply == "draft-ok"
    assert len(planner.calls) == 1
    assert len(critic.calls) == 1
    assert len(executor.calls) == 1
    # План вкладывается в goal как контекст
    assert "План выполнения:" in executor.calls[0]["goal"]
    assert "1) A" in executor.calls[0]["goal"]


async def test_normal_revise_runs_executor_twice(
    conversations: ConversationStore,
) -> None:
    """REVISE → Executor вызывается ещё раз, но в NORMAL — ровно один проход Critic."""

    class _Exec:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self._replies = ["черновик", "финал"]

        async def run(self, **kwargs: Any) -> str:
            self.calls.append(kwargs)
            return self._replies.pop(0) if self._replies else "финал"

    executor = _Exec()
    planner = _FakePlanner()
    critic = _FakeCritic([CriticVerdict(verdict="REVISE", feedback="уточни")])

    reply = await handle_user_task(
        "t", user_id=7, chat_id=1,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="NORMAL"),
        planner=planner, critic=critic,
    )

    assert reply == "финал"
    assert len(executor.calls) == 2
    assert "Замечания: уточни" in executor.calls[1]["goal"]
    assert len(critic.calls) == 1  # NORMAL → одна итерация


async def test_deep_iterates_until_pass_or_limit(
    conversations: ConversationStore,
) -> None:
    """DEEP: Critic итерируется до `agent_reflection_max_iterations`."""

    class _Exec:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self._counter = 0

        async def run(self, **kwargs: Any) -> str:
            self._counter += 1
            self.calls.append(kwargs)
            return f"draft-{self._counter}"

    executor = _Exec()
    planner = _FakePlanner()
    # 3 REVISE подряд → лимит max_iter=2 должен остановить
    critic = _FakeCritic([
        CriticVerdict(verdict="REVISE", feedback="f1"),
        CriticVerdict(verdict="REVISE", feedback="f2"),
        CriticVerdict(verdict="REVISE", feedback="f3"),
    ])

    reply = await handle_user_task(
        "t", user_id=1, chat_id=1,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="DEEP", max_iter=2),
        planner=planner, critic=critic,
    )

    # 1 первоначальный draft + 2 ревизии = 3 вызова executor
    assert len(executor.calls) == 3
    assert len(critic.calls) == 2
    assert reply == "draft-3"


async def test_deep_pass_on_second_iter(
    conversations: ConversationStore,
) -> None:
    class _Exec:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self._i = 0

        async def run(self, **kwargs: Any) -> str:
            self._i += 1
            self.calls.append(kwargs)
            return f"d{self._i}"

    executor = _Exec()
    planner = _FakePlanner()
    critic = _FakeCritic([
        CriticVerdict(verdict="REVISE", feedback="fix"),
        CriticVerdict(verdict="PASS", feedback=""),
    ])

    reply = await handle_user_task(
        "t", user_id=1, chat_id=1,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="DEEP", max_iter=3),
        planner=planner, critic=critic,
    )

    assert reply == "d2"
    assert len(executor.calls) == 2
    assert len(critic.calls) == 2


async def test_user_settings_overrides_settings_mode(
    conversations: ConversationStore,
) -> None:
    """Per-user `reflection_mode` имеет приоритет над `Settings`."""
    executor = _FakeExecutor("ok")
    planner = _FakePlanner()
    critic = _FakeCritic([CriticVerdict(verdict="PASS", feedback="")])

    await handle_user_task(
        "t", user_id=1, chat_id=1,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="OFF"),
        user_settings=_Registry(mode="NORMAL"),
        planner=planner, critic=critic,
    )
    assert len(planner.calls) == 1


async def test_planner_exception_does_not_break_request(
    conversations: ConversationStore,
) -> None:
    """Ошибка Planner на верхнем уровне не должна валить запрос — fallback на Executor."""
    executor = _FakeExecutor("ok-fallback")
    planner = _FakePlanner(exc=RuntimeError("planner down"))
    critic = _FakeCritic([CriticVerdict(verdict="PASS", feedback="")])

    reply = await handle_user_task(
        "t", user_id=1, chat_id=1,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="NORMAL"),
        planner=planner, critic=critic,
    )

    assert reply == "ok-fallback"
    assert len(executor.calls) == 1
    assert executor.calls[0]["goal"] == "t"  # без плана
    assert critic.calls == []


async def test_critic_exception_returns_last_draft(
    conversations: ConversationStore,
) -> None:
    class _BrokenCritic:
        async def review(self, *args: Any, **kwargs: Any) -> CriticVerdict:
            raise RuntimeError("critic exploded")

    executor = _FakeExecutor("draft-only")
    planner = _FakePlanner()

    reply = await handle_user_task(
        "t", user_id=1, chat_id=1,
        conversations=conversations, executor=executor,
        settings=_ReflSettings(mode="NORMAL"),
        planner=planner, critic=_BrokenCritic(),
    )
    assert reply == "draft-only"
