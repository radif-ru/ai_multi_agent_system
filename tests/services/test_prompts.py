"""Тесты `app.services.prompts.PromptLoader`.

Покрывают сценарии из `_docs/testing.md` §3.10.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
