"""Сквозной интеграционный тест мульти-агентной оркестрации.

Сценарий из `_board/sprints/07-multi-agent.md` §7 (задача 4.3): пользователь
вызывает `core.handle_user_task` в режиме `DEEP`, мок-LLM возвращает по
очереди: план → черновик Executor'а → REVISE feedback → улучшенный draft →
PASS. Проверяем итоговый текст, точное число вызовов LLM и порядок
запросов (ровно: planner, executor#1, critic#1, executor#2, critic#2).

Тест работает на реальных `PlannerAgent`/`CriticAgent`/`Executor` — это и
делает его сквозным, в отличие от unit-тестов в `tests/core/`. Сеть не
дёргается: `OllamaClient` подменён `_FakeLLM`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.agents.critic import CriticAgent
from app.agents.executor import Executor
from app.agents.planner import PlannerAgent
from app.core.orchestrator import handle_user_task
from app.services.conversation import ConversationStore


@dataclass
class _Settings:
    agent_max_steps: int = 5
    agent_max_output_chars: int = 8000
    agent_max_context_chars: int = 8000
    ollama_default_model: str = "qwen3.5:4b"
    embedding_model: str = "nomic-embed-text"
    session_bootstrap_enabled: bool = False
    session_bootstrap_top_k: int = 3
    agent_reflection_mode: str = "DEEP"
    agent_reflection_max_iterations: int = 3


class _RecordingLLM:
    """Очередь ответов + точная запись вызовов с тегом из system prompt."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, messages, *, model: str) -> str:
        # Тег запроса = первая встреченная «опознавательная» подстрока в сообщениях.
        # Planner/Critic шлют свой шаблон как `user`, Executor — как `system`.
        joined = " | ".join(m.get("content", "") for m in messages)
        if "PLANNER_SYSTEM" in joined:
            tag = "PLANNER"
        elif "CRITIC_SYSTEM" in joined:
            tag = "CRITIC"
        elif "EXECUTOR_SYSTEM" in joined:
            tag = "EXECUTOR"
        else:
            tag = "UNKNOWN"
        last_user = next(
            (m["content"][:200] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        self.calls.append({"tag": tag, "last_user": last_user, "model": model})
        if not self._responses:
            raise AssertionError("LLM called more times than expected")
        return self._responses.pop(0)


class _Tools:
    def list_descriptions(self):
        return [{"name": "noop", "description": "—", "args_schema": {"type": "object"}}]

    async def execute(self, *args, **kwargs):  # pragma: no cover — Executor сразу даёт final_answer
        raise AssertionError("tools.execute should not be called in this scenario")


class _Skills:
    def list_descriptions(self):
        return []


class _Prompts:
    """Минимальный prompt-loader: разные системные префиксы у разных промптов.

    Это нужно, чтобы по `system`-сообщению в записях LLM-мока легко отличить,
    кто его дёрнул (Executor / Planner / Critic).
    """

    agent_system_template = "EXECUTOR_SYSTEM"

    def render_agent_system(self, *, tools_description: str, skills_description: str) -> str:
        return f"EXECUTOR_SYSTEM tools={tools_description!r} skills={skills_description!r}"

    def render_planner(self, task: str) -> str:
        return f"PLANNER_SYSTEM task={task}"

    def render_critic(self, task, plan, draft) -> str:
        return f"CRITIC_SYSTEM task={task} draft={draft}"


@pytest.mark.asyncio
async def test_deep_full_cycle_plan_revise_pass() -> None:
    settings = _Settings()
    llm = _RecordingLLM(
        responses=[
            # 1) Planner → план из 2 шагов
            json.dumps({"steps": [
                {"id": 1, "description": "проанализировать"},
                {"id": 2, "description": "ответить"},
            ]}),
            # 2) Executor → первый draft (final_answer сразу)
            json.dumps({"final_answer": "draft v1"}),
            # 3) Critic → REVISE с фидбеком
            json.dumps({"verdict": "REVISE", "feedback": "уточни вывод"}),
            # 4) Executor → улучшенный draft
            json.dumps({"final_answer": "draft v2"}),
            # 5) Critic → PASS
            json.dumps({"verdict": "PASS", "feedback": ""}),
        ]
    )

    tools = _Tools()
    skills = _Skills()
    prompts = _Prompts()

    executor = Executor(
        settings=settings, llm=llm, tools=tools, prompts=prompts, skills=skills,
    )
    planner = PlannerAgent(llm=llm, prompts=prompts, settings=settings)
    critic = CriticAgent(llm=llm, prompts=prompts, settings=settings)

    conversations = ConversationStore(max_messages=20)
    conversations.add_user_message(42, "сложная задача")

    reply = await handle_user_task(
        "сложная задача",
        user_id=42,
        chat_id=777,
        conversations=conversations,
        executor=executor,
        settings=settings,
        planner=planner,
        critic=critic,
    )

    assert reply == "draft v2"
    # Ровно 5 LLM-вызовов: planner + 2×executor + 2×critic.
    assert len(llm.calls) == 5
    tags = [c["tag"] for c in llm.calls]
    assert tags == ["PLANNER", "EXECUTOR", "CRITIC", "EXECUTOR", "CRITIC"]
    # Во второй вызов Executor'а уходит фидбек Critic'а.
    assert "уточни вывод" in llm.calls[3]["last_user"]
    # План попадает в первый Executor-вызов как контекст.
    assert "План выполнения" in llm.calls[1]["last_user"]
