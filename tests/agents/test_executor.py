"""Тесты `app.agents.executor.Executor` (агентный цикл).

Покрывает все случаи `_docs/testing.md` §3.4.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import pytest

from app.agents.executor import Executor
from app.services.llm import LLMBadResponse
from app.tools.errors import ArgsValidationError, ToolError, ToolNotFound


@dataclass
class FakeSettings:
    agent_max_steps: int = 5
    agent_max_output_chars: int = 8000
    ollama_default_model: str = "qwen3.5:4b"


class FakeLLM:
    """LLM-мок: возвращает заранее заданные ответы по очереди."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages, *, model: str) -> str:
        self.calls.append([dict(m) for m in messages])
        if not self._responses:
            raise AssertionError("LLM called more times than expected")
        return self._responses.pop(0)


class FakeTools:
    """Tool-реестр-мок с программируемым результатом execute."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, object]] = []
        self._results: list = []
        self._descriptions: list[dict] = [
            {
                "name": "calculator",
                "description": "Calc",
                "args_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            }
        ]

    def queue(self, *results) -> None:
        self._results.extend(results)

    def list_descriptions(self):
        return list(self._descriptions)

    async def execute(self, name, args, ctx):
        self.calls.append((name, dict(args), ctx))
        if not self._results:
            raise AssertionError("tool called more times than expected")
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class FakePrompts:
    def render_agent_system(self, *, tools_description: str, skills_description: str):
        return f"SYSTEM\nTOOLS:\n{tools_description}\nSKILLS:\n{skills_description}"


class FakeSkills:
    def list_descriptions(self):
        return [{"name": "example", "description": "пример скилла"}]


def make_executor(*, llm, tools=None, settings=None) -> Executor:
    return Executor(
        settings=settings or FakeSettings(),
        llm=llm,
        tools=tools or FakeTools(),
        prompts=FakePrompts(),
        skills=FakeSkills(),
    )


async def run_default(executor: Executor) -> str:
    return await executor.run(
        goal="спроси", user_id=42, chat_id=42, conversation_id="conv-1"
    )


async def test_final_on_first_step_no_tool_calls(caplog):
    llm = FakeLLM([json.dumps({"final_answer": "готово"})])
    tools = FakeTools()
    executor = make_executor(llm=llm, tools=tools)

    with caplog.at_level(logging.INFO, logger="app.agents.executor"):
        result = await run_default(executor)

    assert result == "готово"
    assert tools.calls == []
    assert any("step=1" in r.message and "kind=final" in r.message for r in caplog.records)


async def test_final_on_third_step_tools_called_twice(caplog):
    llm = FakeLLM([
        json.dumps({"thought": "1", "action": "calculator", "args": {"expression": "1+1"}}),
        json.dumps({"thought": "2", "action": "calculator", "args": {"expression": "2+2"}}),
        json.dumps({"final_answer": "результат 4"}),
    ])
    tools = FakeTools()
    tools.queue("2", "4")
    executor = make_executor(llm=llm, tools=tools)

    with caplog.at_level(logging.INFO, logger="app.agents.executor"):
        result = await run_default(executor)

    assert result == "результат 4"
    assert [c[0] for c in tools.calls] == ["calculator", "calculator"]
    assert tools.calls[0][1] == {"expression": "1+1"}
    assert tools.calls[1][1] == {"expression": "2+2"}

    # На втором вызове LLM в messages должна попасть observation от первого tool.
    second_call_msgs = llm.calls[1]
    assert second_call_msgs[-1]["role"] == "user"
    assert second_call_msgs[-1]["content"] == "Observation: 2"
    assert second_call_msgs[-2]["role"] == "assistant"

    # Логи: step=1, step=2 kind=action; step=3 kind=final.
    msgs = [r.message for r in caplog.records]
    assert any("step=1" in m and "kind=action" in m for m in msgs)
    assert any("step=2" in m and "kind=action" in m for m in msgs)
    assert any("step=3" in m and "kind=final" in m for m in msgs)


async def test_tool_error_becomes_observation_and_loop_continues():
    llm = FakeLLM([
        json.dumps({"thought": "1", "action": "calculator", "args": {"expression": "x"}}),
        json.dumps({"final_answer": "поправил"}),
    ])
    tools = FakeTools()
    tools.queue(ToolError("bad expression"))
    executor = make_executor(llm=llm, tools=tools)

    result = await run_default(executor)

    assert result == "поправил"
    assert llm.calls[1][-1]["content"] == "Observation: Tool error: bad expression"


async def test_bad_json_raises_llm_bad_response(caplog):
    llm = FakeLLM(["не json вообще"])
    executor = make_executor(llm=llm)

    with caplog.at_level(logging.WARNING, logger="app.agents.executor"):
        with pytest.raises(LLMBadResponse):
            await run_default(executor)

    assert any("kind=parse_error" in r.message for r in caplog.records)


async def test_max_steps_exceeded_returns_specific_message():
    settings = FakeSettings(agent_max_steps=2)
    llm = FakeLLM([
        json.dumps({"thought": "a", "action": "calculator", "args": {"expression": "1"}}),
        json.dumps({"thought": "b", "action": "calculator", "args": {"expression": "2"}}),
    ])
    tools = FakeTools()
    tools.queue("ok1", "ok2")
    executor = make_executor(llm=llm, tools=tools, settings=settings)

    result = await executor.run(
        goal="g", user_id=1, chat_id=1, conversation_id="c"
    )

    assert "2 шагов" in result
    assert len(tools.calls) == 2


async def test_response_too_large_raises_llm_bad_response():
    settings = FakeSettings(agent_max_output_chars=10)
    llm = FakeLLM(["x" * 11])
    executor = make_executor(llm=llm, settings=settings)

    with pytest.raises(LLMBadResponse):
        await run_default(executor)


async def test_unknown_tool_becomes_observation():
    """ToolNotFound теперь возвращает observation вместо исключения."""
    llm = FakeLLM([
        json.dumps({"thought": "t", "action": "unknown", "args": {}}),
        json.dumps({"final_answer": "попробую другой tool"}),
    ])
    tools = FakeTools()
    tools.queue(ToolNotFound("unknown"))
    executor = make_executor(llm=llm, tools=tools)

    result = await run_default(executor)
    assert result == "попробую другой tool"


async def test_args_validation_error_becomes_observation():
    """ArgsValidationError теперь возвращает observation вместо исключения."""
    llm = FakeLLM([
        json.dumps({"thought": "t", "action": "calculator", "args": {"expression": 1}}),
        json.dumps({"final_answer": "исправил"}),
    ])
    tools = FakeTools()
    tools.queue(ArgsValidationError("expression must be string"))
    executor = make_executor(llm=llm, tools=tools)

    result = await run_default(executor)
    assert result == "исправил"


async def test_system_prompt_built_with_tools_and_skills():
    llm = FakeLLM([json.dumps({"final_answer": "ok"})])
    executor = make_executor(llm=llm)

    await run_default(executor)

    system_msg = llm.calls[0][0]
    assert system_msg["role"] == "system"
    assert "calculator" in system_msg["content"]
    assert "example" in system_msg["content"]


async def test_executor_uses_history():
    """`history` склеивается между system и goal в порядке поступления."""
    llm = FakeLLM([json.dumps({"final_answer": "ок"})])
    executor = make_executor(llm=llm)

    history = [
        {"role": "user", "content": "Привет, я Радиф"},
        {"role": "assistant", "content": "Привет, Радиф"},
        {"role": "user", "content": "Как меня зовут?"},
    ]

    await executor.run(
        goal="Как меня зовут?",
        user_id=1,
        chat_id=1,
        conversation_id="c",
        history=history,
    )

    msgs = llm.calls[0]
    assert msgs[0]["role"] == "system"
    # Последний user-message в `history` совпадает с `goal` → дубликата нет.
    assert msgs[1:] == history


async def test_executor_appends_goal_when_history_does_not_end_with_it():
    """Если `history` не заканчивается goal-сообщением — `goal` дописывается."""
    llm = FakeLLM([json.dumps({"final_answer": "ок"})])
    executor = make_executor(llm=llm)

    history = [
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Привет!"},
    ]

    await executor.run(
        goal="Как дела?",
        user_id=1,
        chat_id=1,
        conversation_id="c",
        history=history,
    )

    msgs = llm.calls[0]
    assert msgs[0]["role"] == "system"
    assert msgs[1:-1] == history
    assert msgs[-1] == {"role": "user", "content": "Как дела?"}


async def test_executor_history_none_back_compat():
    """`history=None` (или отсутствует) → поведение Спринта 01."""
    llm = FakeLLM([json.dumps({"final_answer": "ок"})])
    executor = make_executor(llm=llm)

    await executor.run(
        goal="спроси", user_id=1, chat_id=1, conversation_id="c"
    )

    msgs = llm.calls[0]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "спроси"}


async def test_tool_context_passed_with_user_and_conversation():
    llm = FakeLLM([
        json.dumps({"thought": "t", "action": "calculator", "args": {"expression": "1"}}),
        json.dumps({"final_answer": "ok"}),
    ])
    tools = FakeTools()
    tools.queue("1")
    executor = make_executor(llm=llm, tools=tools)

    await executor.run(
        goal="g", user_id=99, chat_id=100, conversation_id="abc"
    )

    _, _, ctx = tools.calls[0]
    assert ctx.user_id == 99
    assert ctx.chat_id == 100
    assert ctx.conversation_id == "abc"
