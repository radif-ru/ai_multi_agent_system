"""Тесты `app.services.prompts.PromptLoader`.

Покрывают сценарии из `_docs/testing.md` §3.10.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.protocol import Plan, PlanStep
from app.services.prompts import PromptLoader


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_reads_both_files_into_strings(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "AGENT TEMPLATE")
    summ = _write(tmp_path / "summarizer.md", "SUMMARIZER PROMPT")

    loader = PromptLoader(agent, summ)

    assert loader.agent_system_template == "AGENT TEMPLATE"
    assert loader.summarizer_prompt == "SUMMARIZER PROMPT"


def test_missing_agent_system_raises(tmp_path: Path) -> None:
    summ = _write(tmp_path / "summarizer.md", "x")
    with pytest.raises(FileNotFoundError):
        PromptLoader(tmp_path / "no.md", summ)


def test_missing_summarizer_raises(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    with pytest.raises(FileNotFoundError):
        PromptLoader(agent, tmp_path / "no.md")


def test_substitutes_tools_description(tmp_path: Path) -> None:
    agent = _write(
        tmp_path / "agent_system.md",
        "Tools:\n{{TOOLS_DESCRIPTION}}\nEnd.",
    )
    summ = _write(tmp_path / "summarizer.md", "")
    loader = PromptLoader(agent, summ)

    out = loader.render_agent_system(
        tools_description="- calc(x): do math.",
        skills_description="",
    )
    assert "- calc(x): do math." in out
    assert "{{TOOLS_DESCRIPTION}}" not in out


def test_substitutes_skills_description(tmp_path: Path) -> None:
    agent = _write(
        tmp_path / "agent_system.md",
        "Skills:\n{{SKILLS_DESCRIPTION}}\n",
    )
    summ = _write(tmp_path / "summarizer.md", "")
    loader = PromptLoader(agent, summ)

    out = loader.render_agent_system(
        tools_description="",
        skills_description="- alpha: первый.",
    )
    assert "- alpha: первый." in out
    assert "{{SKILLS_DESCRIPTION}}" not in out


def test_missing_placeholder_is_not_error(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "Без плейсхолдеров.")
    summ = _write(tmp_path / "summarizer.md", "")
    loader = PromptLoader(agent, summ)

    out = loader.render_agent_system(
        tools_description="ignored",
        skills_description="ignored",
    )
    assert out == "Без плейсхолдеров."


def test_reads_planner_template(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    planner = _write(tmp_path / "planner.md", "PLANNER {{TASK}}")
    loader = PromptLoader(agent, summ, planner)
    assert loader.planner_template == "PLANNER {{TASK}}"


def test_missing_planner_raises(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    with pytest.raises(FileNotFoundError):
        PromptLoader(agent, summ, tmp_path / "no.md")


def test_render_planner_substitutes_task(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    planner = _write(tmp_path / "planner.md", "Задача: {{TASK}}\nКонец.")
    loader = PromptLoader(agent, summ, planner)

    out = loader.render_planner("найти столицу Франции")
    assert out == "Задача: найти столицу Франции\nКонец."
    assert "{{TASK}}" not in out


def test_render_planner_without_placeholder_is_not_error(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    planner = _write(tmp_path / "planner.md", "Без плейсхолдера.")
    loader = PromptLoader(agent, summ, planner)
    assert loader.render_planner("любая задача") == "Без плейсхолдера."


def test_planner_template_is_not_mutated_between_renders(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    planner = _write(tmp_path / "planner.md", "T={{TASK}}")
    loader = PromptLoader(agent, summ, planner)
    assert loader.render_planner("A") == "T=A"
    assert loader.render_planner("B") == "T=B"
    assert "{{TASK}}" in loader.planner_template


def _critic_loader(tmp_path: Path, critic_body: str) -> PromptLoader:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    planner = _write(tmp_path / "planner.md", "p")
    critic = _write(tmp_path / "critic.md", critic_body)
    return PromptLoader(agent, summ, planner, critic)


def test_reads_critic_template(tmp_path: Path) -> None:
    loader = _critic_loader(tmp_path, "CRITIC {{TASK}} {{PLAN}} {{DRAFT}}")
    assert loader.critic_template == "CRITIC {{TASK}} {{PLAN}} {{DRAFT}}"


def test_missing_critic_raises(tmp_path: Path) -> None:
    agent = _write(tmp_path / "agent_system.md", "x")
    summ = _write(tmp_path / "summarizer.md", "y")
    planner = _write(tmp_path / "planner.md", "p")
    with pytest.raises(FileNotFoundError):
        PromptLoader(agent, summ, planner, tmp_path / "no.md")


def test_render_critic_substitutes_all_placeholders(tmp_path: Path) -> None:
    loader = _critic_loader(
        tmp_path,
        "T={{TASK}}\nP=\n{{PLAN}}\nD={{DRAFT}}",
    )
    plan = Plan(
        steps=(
            PlanStep(id=1, description="первый шаг"),
            PlanStep(id=2, description="второй шаг"),
        )
    )
    out = loader.render_critic("найти X", plan, "черновик ответа")
    assert "T=найти X" in out
    assert "1. первый шаг\n2. второй шаг" in out
    assert "D=черновик ответа" in out
    assert "{{TASK}}" not in out
    assert "{{PLAN}}" not in out
    assert "{{DRAFT}}" not in out


def test_render_critic_single_step_plan(tmp_path: Path) -> None:
    loader = _critic_loader(tmp_path, "{{PLAN}}")
    plan = Plan(steps=(PlanStep(id=1, description="всё в одном шаге"),))
    assert loader.render_critic("t", plan, "d") == "1. всё в одном шаге"


def test_render_critic_without_placeholders_is_not_error(tmp_path: Path) -> None:
    loader = _critic_loader(tmp_path, "Без плейсхолдеров.")
    plan = Plan(steps=(PlanStep(id=1, description="x"),))
    assert loader.render_critic("t", plan, "d") == "Без плейсхолдеров."


def test_critic_template_is_not_mutated_between_renders(tmp_path: Path) -> None:
    loader = _critic_loader(tmp_path, "T={{TASK}}|P={{PLAN}}|D={{DRAFT}}")
    plan = Plan(steps=(PlanStep(id=1, description="s"),))
    first = loader.render_critic("A", plan, "DA")
    second = loader.render_critic("B", plan, "DB")
    assert first == "T=A|P=1. s|D=DA"
    assert second == "T=B|P=1. s|D=DB"
    assert "{{TASK}}" in loader.critic_template


def test_template_is_not_mutated_between_renders(tmp_path: Path) -> None:
    agent = _write(
        tmp_path / "agent_system.md",
        "{{TOOLS_DESCRIPTION}} | {{SKILLS_DESCRIPTION}}",
    )
    summ = _write(tmp_path / "summarizer.md", "")
    loader = PromptLoader(agent, summ)

    first = loader.render_agent_system(tools_description="A", skills_description="B")
    second = loader.render_agent_system(tools_description="X", skills_description="Y")

    assert first == "A | B"
    assert second == "X | Y"
    assert "{{TOOLS_DESCRIPTION}}" in loader.agent_system_template
