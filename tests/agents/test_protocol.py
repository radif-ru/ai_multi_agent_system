"""Тесты парсера JSON-ответа модели.

Покрывает все случаи `_docs/testing.md` §3.3.
"""

from __future__ import annotations

import json

import pytest

from app.agents.protocol import AgentDecision, parse_agent_response
from app.services.llm import LLMBadResponse


def test_parse_action_valid():
    text = json.dumps(
        {"thought": "посчитать", "action": "calculator", "args": {"expression": "1+2"}}
    )
    d = parse_agent_response(text)
    assert d == AgentDecision(
        kind="action",
        thought="посчитать",
        action="calculator",
        args={"expression": "1+2"},
    )


def test_parse_action_empty_args_object_ok():
    text = json.dumps({"thought": "t", "action": "noop", "args": {}})
    d = parse_agent_response(text)
    assert d.kind == "action"
    assert d.args == {}


def test_parse_final_valid():
    text = json.dumps({"final_answer": "ответ"})
    d = parse_agent_response(text)
    assert d == AgentDecision(kind="final", final_answer="ответ")


def test_invalid_json_raises():
    with pytest.raises(LLMBadResponse):
        parse_agent_response("{not json")


@pytest.mark.parametrize("payload", ["[]", '"str"', "42", "null"])
def test_non_object_raises(payload):
    with pytest.raises(LLMBadResponse):
        parse_agent_response(payload)


def test_mixed_format_raises():
    text = json.dumps(
        {"thought": "t", "action": "a", "args": {}, "final_answer": "x"}
    )
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_thought_raises(value):
    text = json.dumps({"thought": value, "action": "a", "args": {}})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_final_answer_raises(value):
    text = json.dumps({"final_answer": value})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_action_without_args_raises():
    text = json.dumps({"thought": "t", "action": "a"})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_action_without_thought_raises():
    text = json.dumps({"action": "a", "args": {}})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_action_without_action_raises():
    text = json.dumps({"thought": "t", "args": {}})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_args_not_object_raises():
    text = json.dumps({"thought": "t", "action": "a", "args": [1, 2]})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_thought_not_string_raises():
    text = json.dumps({"thought": 42, "action": "a", "args": {}})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_action_not_string_raises():
    text = json.dumps({"thought": "t", "action": 42, "args": {}})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_final_answer_not_string_raises():
    text = json.dumps({"final_answer": 123})
    with pytest.raises(LLMBadResponse):
        parse_agent_response(text)


def test_parse_with_json_fence():
    """Парсер снимает ```json ... ``` обёртку."""
    text = """```json
{
  "thought": "посчитать",
  "action": "calculator",
  "args": {"expression": "1+2"}
}
```"""
    d = parse_agent_response(text)
    assert d == AgentDecision(
        kind="action",
        thought="посчитать",
        action="calculator",
        args={"expression": "1+2"},
    )


def test_parse_with_plain_fence():
    """Парсер снимает ``` ... ``` обёртку без указания языка."""
    text = """```
{
  "final_answer": "ответ"
}
```"""
    d = parse_agent_response(text)
    assert d == AgentDecision(kind="final", final_answer="ответ")


def test_parse_with_fence_and_whitespace():
    """Парсер снимает fence с обрамляющими пробелами."""
    text = """
  ```json
  {"final_answer": "ответ"}
  ```
  """
    d = parse_agent_response(text)
    assert d == AgentDecision(kind="final", final_answer="ответ")


def test_parse_bare_json_back_compat():
    """Голый JSON без fence парсится как раньше (бэк-компат)."""
    text = json.dumps({"final_answer": "ответ"})
    d = parse_agent_response(text)
    assert d == AgentDecision(kind="final", final_answer="ответ")


def test_parse_invalid_json_inside_fence_raises():
    """Невалидный JSON внутри fence → LLMBadResponse."""
    text = """```json
{not valid json}
```"""
    with pytest.raises(LLMBadResponse, match="invalid JSON"):
        parse_agent_response(text)
