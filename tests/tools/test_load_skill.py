"""Тесты `app.tools.load_skill.LoadSkillTool`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.errors import ToolError
from app.tools.load_skill import LoadSkillTool


class _FakeSkills:
    def __init__(self, bodies: dict[str, str]) -> None:
        self._bodies = bodies

    def get_body(self, name: str) -> str:
        return self._bodies[name]


def _ctx(skills) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=1, chat_id=1, conversation_id="c",
        settings=None, llm=None, semantic_memory=None, skills=skills,
    )


async def test_returns_body_for_existing_skill():
    ctx = _ctx(_FakeSkills({"summary": "Body of skill\nline 2"}))
    tool = LoadSkillTool()
    out = await tool.run({"name": "summary"}, ctx)
    assert out == "Body of skill\nline 2"


async def test_missing_skill_raises_tool_error():
    ctx = _ctx(_FakeSkills({}))
    tool = LoadSkillTool()
    with pytest.raises(ToolError, match="skill not found"):
        await tool.run({"name": "missing"}, ctx)


async def test_empty_name_rejected():
    ctx = _ctx(_FakeSkills({}))
    tool = LoadSkillTool()
    with pytest.raises(ToolError):
        await tool.run({"name": "  "}, ctx)


async def test_truncation():
    ctx = _ctx(_FakeSkills({"big": "x" * 5000}))
    tool = LoadSkillTool(max_output_chars=100)
    out = await tool.run({"name": "big"}, ctx)
    assert len(out) == 100
    assert out.endswith("[truncated]")
