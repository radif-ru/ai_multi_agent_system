"""Тесты парсеров multi-agent протокола (Planner / Critic).

Покрывают задачу 1.2 спринта 07 (см. `_board/sprints/07-multi-agent.md`).
"""

from __future__ import annotations

import json

import pytest

from app.agents.protocol import (
    CriticVerdict,
    Plan,
    PlanStep,
    parse_critic_response,
    parse_planner_response,
)
from app.services.llm import LLMBadResponse


# --- Planner ---------------------------------------------------------------


def test_parse_planner_valid_single_step():
    text = json.dumps({"steps": [{"id": 1, "description": "Найти информацию"}]})
    plan = parse_planner_response(text)
    assert plan == Plan(steps=(PlanStep(id=1, description="Найти информацию"),))


def test_parse_planner_valid_multiple_steps():
    text = json.dumps(
        {
            "steps": [
                {"id": 1, "description": "Шаг один"},
                {"id": 2, "description": "Шаг два"},
                {"id": 3, "description": "Шаг три"},
            ]
        }
    )
    plan = parse_planner_response(text)
    assert len(plan.steps) == 3
    assert plan.steps[2] == PlanStep(id=3, description="Шаг три")


def test_parse_planner_markdown_fence_stripped():
    payload = {"steps": [{"id": 1, "description": "x"}]}
    text = f"```json\n{json.dumps(payload)}\n```"
    plan = parse_planner_response(text)
    assert plan.steps[0].description == "x"


def test_parse_planner_invalid_json_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response("not a json at all")


def test_parse_planner_not_object_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response("[1, 2, 3]")


def test_parse_planner_missing_steps_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response(json.dumps({"plan": []}))


def test_parse_planner_empty_steps_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response(json.dumps({"steps": []}))


def test_parse_planner_too_many_steps_raises():
    steps = [{"id": i, "description": f"s{i}"} for i in range(1, 10)]
    with pytest.raises(LLMBadResponse):
        parse_planner_response(json.dumps({"steps": steps}))


def test_parse_planner_step_not_object_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response(json.dumps({"steps": ["not-an-object"]}))


def test_parse_planner_step_id_not_int_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response(
            json.dumps({"steps": [{"id": "1", "description": "x"}]})
        )


def test_parse_planner_step_description_empty_raises():
    with pytest.raises(LLMBadResponse):
        parse_planner_response(
            json.dumps({"steps": [{"id": 1, "description": "   "}]})
        )


def test_parse_planner_step_description_too_long_raises():
    long_desc = "x" * 201
    with pytest.raises(LLMBadResponse):
        parse_planner_response(
            json.dumps({"steps": [{"id": 1, "description": long_desc}]})
        )


# --- Critic ----------------------------------------------------------------


def test_parse_critic_pass_with_empty_feedback():
    text = json.dumps({"verdict": "PASS", "feedback": ""})
    v = parse_critic_response(text)
    assert v == CriticVerdict(verdict="PASS", feedback="")


def test_parse_critic_pass_without_feedback_field():
    text = json.dumps({"verdict": "PASS"})
    v = parse_critic_response(text)
    assert v.verdict == "PASS"
    assert v.feedback == ""


def test_parse_critic_revise_with_feedback():
    text = json.dumps({"verdict": "REVISE", "feedback": "уточни источники"})
    v = parse_critic_response(text)
    assert v == CriticVerdict(verdict="REVISE", feedback="уточни источники")


def test_parse_critic_markdown_fence_stripped():
    payload = {"verdict": "PASS", "feedback": ""}
    text = f"```\n{json.dumps(payload)}\n```"
    assert parse_critic_response(text).verdict == "PASS"


def test_parse_critic_verdict_case_insensitive():
    text = json.dumps({"verdict": "pass", "feedback": ""})
    assert parse_critic_response(text).verdict == "PASS"


def test_parse_critic_invalid_json_raises():
    with pytest.raises(LLMBadResponse):
        parse_critic_response("totally not json")


def test_parse_critic_unknown_verdict_raises():
    with pytest.raises(LLMBadResponse):
        parse_critic_response(json.dumps({"verdict": "MAYBE", "feedback": "x"}))


def test_parse_critic_verdict_not_string_raises():
    with pytest.raises(LLMBadResponse):
        parse_critic_response(json.dumps({"verdict": 1, "feedback": "x"}))


def test_parse_critic_revise_without_feedback_raises():
    with pytest.raises(LLMBadResponse):
        parse_critic_response(json.dumps({"verdict": "REVISE", "feedback": ""}))


def test_parse_critic_feedback_not_string_raises():
    with pytest.raises(LLMBadResponse):
        parse_critic_response(json.dumps({"verdict": "PASS", "feedback": 123}))
