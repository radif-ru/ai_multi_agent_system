"""Тесты `PlannerAgent`.

Покрывают задачу 2.2 спринта 07 (см. `_board/sprints/07-multi-agent.md`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import pytest

from app.agents.planner import PlannerAgent
from app.agents.protocol import Plan, PlanStep
from app.services.llm import LLMBadResponse, LLMTimeout


@dataclass
class _Settings:
    ollama_default_model: str = "qwen3.5:4b"


class _Prompts:
    def render_planner(self, task: str) -> str:
        return f"PLANNER PROMPT: {task}"


class _FakeLLM:
    def __init__(self, response: str | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages, *, model, **kwargs):
        self.calls.append({"messages": list(messages), "model": model})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _make_agent(response: str | Exception) -> tuple[PlannerAgent, _FakeLLM]:
    llm = _FakeLLM(response)
    agent = PlannerAgent(llm=llm, prompts=_Prompts(), settings=_Settings())
    return agent, llm


# --- happy paths ----------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_happy_path():
    payload = {
        "steps": [
            {"id": 1, "description": "Понять запрос"},
            {"id": 2, "description": "Сформулировать ответ"},
        ]
    }
    agent, llm = _make_agent(json.dumps(payload))
    plan = await agent.plan("Что такое RAG?", user_id=42)

    assert plan == Plan(
        steps=(
            PlanStep(id=1, description="Понять запрос"),
            PlanStep(id=2, description="Сформулировать ответ"),
        )
    )
    assert llm.calls[0]["model"] == "qwen3.5:4b"
    assert "Что такое RAG?" in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_plan_uses_explicit_model():
    payload = {"steps": [{"id": 1, "description": "x"}]}
    agent, llm = _make_agent(json.dumps(payload))
    await agent.plan("задача", user_id=1, model="custom:7b")
    assert llm.calls[0]["model"] == "custom:7b"


@pytest.mark.asyncio
async def test_plan_markdown_fence_is_tolerated():
    payload = {"steps": [{"id": 1, "description": "шаг"}]}
    raw = f"```json\n{json.dumps(payload)}\n```"
    agent, _ = _make_agent(raw)
    plan = await agent.plan("t", user_id=1)
    assert plan.steps[0].description == "шаг"


# --- fallback branches ----------------------------------------------------


@pytest.mark.asyncio
async def test_plan_fallback_on_garbage(caplog):
    agent, _ = _make_agent("not a json")
    with caplog.at_level(logging.WARNING):
        plan = await agent.plan("исходная задача", user_id=7)
    assert plan == Plan(steps=(PlanStep(id=1, description="исходная задача"),))
    assert any("planner.fallback" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_plan_fallback_on_empty_steps():
    agent, _ = _make_agent(json.dumps({"steps": []}))
    plan = await agent.plan("исходная задача", user_id=7)
    assert plan.steps == (PlanStep(id=1, description="исходная задача"),)


@pytest.mark.asyncio
async def test_plan_fallback_on_llm_error():
    agent, _ = _make_agent(LLMTimeout("boom"))
    plan = await agent.plan("задача", user_id=7)
    assert plan.steps == (PlanStep(id=1, description="задача"),)


@pytest.mark.asyncio
async def test_plan_fallback_truncates_long_task():
    long_task = "x" * 500
    agent, _ = _make_agent("garbage")
    plan = await agent.plan(long_task, user_id=1)
    assert len(plan.steps[0].description) == 200


@pytest.mark.asyncio
async def test_plan_fallback_on_bad_response_parser_error():
    # Невалидный verdict-структура (нет steps) — должно дать fallback.
    agent, _ = _make_agent(json.dumps({"plan": "x"}))
    plan = await agent.plan("t", user_id=1)
    assert plan.steps == (PlanStep(id=1, description="t"),)


@pytest.mark.asyncio
async def test_plan_does_not_swallow_unexpected_exceptions():
    # Если LLM поднимает не-LLMError, мы не должны прятать ошибку.
    agent, _ = _make_agent(RuntimeError("upstream"))
    with pytest.raises(RuntimeError):
        await agent.plan("t", user_id=1)


# Sanity: убеждаемся что LLMBadResponse в самом llm.chat тоже маппится в fallback
@pytest.mark.asyncio
async def test_plan_fallback_on_llm_bad_response():
    agent, _ = _make_agent(LLMBadResponse("empty"))
    plan = await agent.plan("t", user_id=1)
    assert plan.steps == (PlanStep(id=1, description="t"),)
