"""Тесты `CriticAgent`.

Покрывают задачу 3.2 спринта 07 (см. `_board/sprints/07-multi-agent.md`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import pytest

from app.agents.critic import CriticAgent
from app.agents.protocol import CriticVerdict, Plan, PlanStep
from app.services.llm import LLMBadResponse, LLMTimeout


@dataclass
class _Settings:
    ollama_default_model: str = "qwen3.5:4b"


class _Prompts:
    def render_critic(self, task: str, plan: Plan, draft: str) -> str:
        steps = "; ".join(f"{s.id}. {s.description}" for s in plan.steps)
        return f"CRITIC PROMPT task={task} plan=[{steps}] draft={draft}"


class _FakeLLM:
    def __init__(self, response: str | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages, *, model, **kwargs):
        self.calls.append({"messages": list(messages), "model": model})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _make_agent(response: str | Exception) -> tuple[CriticAgent, _FakeLLM]:
    llm = _FakeLLM(response)
    agent = CriticAgent(llm=llm, prompts=_Prompts(), settings=_Settings())
    return agent, llm


_PLAN = Plan(steps=(PlanStep(id=1, description="шаг один"),))


# --- happy paths ----------------------------------------------------------


@pytest.mark.asyncio
async def test_review_pass():
    raw = json.dumps({"verdict": "PASS", "feedback": ""})
    agent, llm = _make_agent(raw)
    verdict = await agent.review("задача", _PLAN, "черновик", user_id=42)
    assert verdict == CriticVerdict(verdict="PASS", feedback="")
    assert llm.calls[0]["model"] == "qwen3.5:4b"
    content = llm.calls[0]["messages"][0]["content"]
    assert "задача" in content and "черновик" in content


@pytest.mark.asyncio
async def test_review_revise_with_feedback():
    raw = json.dumps({"verdict": "REVISE", "feedback": "уточнить факты"})
    agent, _ = _make_agent(raw)
    verdict = await agent.review("t", _PLAN, "d", user_id=1)
    assert verdict.verdict == "REVISE"
    assert verdict.feedback == "уточнить факты"


@pytest.mark.asyncio
async def test_review_uses_explicit_model():
    raw = json.dumps({"verdict": "PASS", "feedback": ""})
    agent, llm = _make_agent(raw)
    await agent.review("t", _PLAN, "d", user_id=1, model="custom:7b")
    assert llm.calls[0]["model"] == "custom:7b"


@pytest.mark.asyncio
async def test_review_markdown_fence_is_tolerated():
    payload = {"verdict": "PASS", "feedback": ""}
    raw = f"```json\n{json.dumps(payload)}\n```"
    agent, _ = _make_agent(raw)
    verdict = await agent.review("t", _PLAN, "d", user_id=1)
    assert verdict.verdict == "PASS"


# --- fallback branches (fail-open) ---------------------------------------


@pytest.mark.asyncio
async def test_review_fallback_on_garbage(caplog):
    agent, _ = _make_agent("not a json")
    with caplog.at_level(logging.WARNING):
        verdict = await agent.review("t", _PLAN, "d", user_id=7)
    assert verdict == CriticVerdict(verdict="PASS", feedback="")
    assert any("critic.fallback" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_review_fallback_on_unknown_verdict():
    raw = json.dumps({"verdict": "MAYBE", "feedback": "..."})
    agent, _ = _make_agent(raw)
    verdict = await agent.review("t", _PLAN, "d", user_id=1)
    assert verdict == CriticVerdict(verdict="PASS", feedback="")


@pytest.mark.asyncio
async def test_review_fallback_on_revise_without_feedback():
    # REVISE без feedback → парсер ругается → fail-open PASS.
    raw = json.dumps({"verdict": "REVISE", "feedback": ""})
    agent, _ = _make_agent(raw)
    verdict = await agent.review("t", _PLAN, "d", user_id=1)
    assert verdict == CriticVerdict(verdict="PASS", feedback="")


@pytest.mark.asyncio
async def test_review_fallback_on_llm_error():
    agent, _ = _make_agent(LLMTimeout("boom"))
    verdict = await agent.review("t", _PLAN, "d", user_id=7)
    assert verdict == CriticVerdict(verdict="PASS", feedback="")


@pytest.mark.asyncio
async def test_review_fallback_on_llm_bad_response():
    agent, _ = _make_agent(LLMBadResponse("empty"))
    verdict = await agent.review("t", _PLAN, "d", user_id=1)
    assert verdict == CriticVerdict(verdict="PASS", feedback="")


@pytest.mark.asyncio
async def test_review_does_not_swallow_unexpected_exceptions():
    agent, _ = _make_agent(RuntimeError("upstream"))
    with pytest.raises(RuntimeError):
        await agent.review("t", _PLAN, "d", user_id=1)
