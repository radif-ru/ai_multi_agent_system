"""Тесты `app.services.skills.SkillRegistry`.

Покрывают сценарии из `_docs/testing.md` §3.9.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.skills import SkillRegistry


def _write_skill(root: Path, name: str, content: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_scans_directory_and_parses_description(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "alpha",
        "Description: первый скилл\n\n# Skill: alpha\n\nТело A\n",
    )
    _write_skill(
        tmp_path,
        "beta",
        "Description: второй скилл\n\nТело B",
    )

    reg = SkillRegistry(tmp_path)
    reg.load()

    assert reg.list_descriptions() == [
        {"name": "alpha", "description": "первый скилл"},
        {"name": "beta", "description": "второй скилл"},
    ]


def test_get_body_returns_content_without_first_line(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "alpha",
        "Description: тест\n\n# Skill: alpha\n\nИнструкция.\n",
    )
    reg = SkillRegistry(tmp_path)
    reg.load()

    body = reg.get_body("alpha")
    assert not body.startswith("Description:")
    assert body == "# Skill: alpha\n\nИнструкция.\n"


def test_get_body_unknown_skill_raises_key_error(tmp_path: Path) -> None:
    reg = SkillRegistry(tmp_path)
    reg.load()
    with pytest.raises(KeyError):
        reg.get_body("missing")


def test_skill_md_without_description_raises(tmp_path: Path) -> None:
    _write_skill(tmp_path, "broken", "# Skill: broken\n\nНет первой строки.\n")
    reg = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="Description"):
        reg.load()


def test_empty_description_raises(tmp_path: Path) -> None:
    _write_skill(tmp_path, "empty-desc", "Description:   \n\nТело.\n")
    reg = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="Пустое описание"):
        reg.load()


def test_ignores_files_and_dirs_without_skill_md(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("not a skill", encoding="utf-8")
    (tmp_path / "no-skill-md").mkdir()
    _write_skill(tmp_path, "alpha", "Description: ok\n\nТело.\n")

    reg = SkillRegistry(tmp_path)
    reg.load()

    assert [d["name"] for d in reg.list_descriptions()] == ["alpha"]


def test_missing_directory_results_in_empty_registry(tmp_path: Path) -> None:
    reg = SkillRegistry(tmp_path / "does-not-exist")
    reg.load()
    assert reg.list_descriptions() == []


def test_yaml_frontmatter_parsed_correctly(tmp_path: Path) -> None:
    """YAML frontmatter с description парсится корректно."""
    _write_skill(
        tmp_path,
        "yaml-skill",
        "---\nname: yaml-skill\ndescription: \"YAML skill description\"\nrisk: unknown\n---\n\n# Body\n\nContent.\n",
    )
    reg = SkillRegistry(tmp_path)
    reg.load()

    assert reg.list_descriptions() == [
        {"name": "yaml-skill", "description": "YAML skill description"},
    ]
    body = reg.get_body("yaml-skill")
    assert "# Body" in body
    assert "description:" not in body  # frontmatter отделен


def test_yaml_frontmatter_multiline_description(tmp_path: Path) -> None:
    """YAML frontmatter с многострочным description."""
    _write_skill(
        tmp_path,
        "multiline",
        '---\ndescription: |\n  Line one\n  Line two\n---\n\nBody.\n',
    )
    reg = SkillRegistry(tmp_path)
    reg.load()

    desc = reg.list_descriptions()[0]["description"]
    assert "Line one" in desc
    assert "Line two" in desc


def test_legacy_and_yaml_skills_together(tmp_path: Path) -> None:
    """Legacy и YAML скиллы работают вместе."""
    _write_skill(
        tmp_path,
        "legacy",
        "Description: legacy skill\n\nLegacy body.\n",
    )
    _write_skill(
        tmp_path,
        "yaml",
        "---\ndescription: yaml skill\n---\n\nYAML body.\n",
    )
    reg = SkillRegistry(tmp_path)
    reg.load()

    descs = reg.list_descriptions()
    assert len(descs) == 2
    names = {d["name"] for d in descs}
    assert names == {"legacy", "yaml"}


def test_yaml_frontmatter_invalid_yaml_raises(tmp_path: Path) -> None:
    """Невалидный YAML вызывает ValueError."""
    _write_skill(
        tmp_path,
        "invalid-yaml",
        "---\n[invalid yaml: : :\n---\n\nBody.\n",
    )
    reg = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="YAML"):
        reg.load()


def test_yaml_frontmatter_empty_description_raises(tmp_path: Path) -> None:
    """Пустое description в YAML frontmatter вызывает ValueError."""
    _write_skill(
        tmp_path,
        "empty-yaml",
        "---\nname: test\n---\n\nBody.\n",
    )
    reg = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="Пустое описание"):
        reg.load()
