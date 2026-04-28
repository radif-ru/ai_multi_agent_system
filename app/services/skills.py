"""SkillRegistry — сканирование `_skills/` и парсинг `SKILL.md`.

См. `_docs/skills.md` §3 (формат) и §4 (как агент использует).

Каждая подпапка `_skills/<name>/` с файлом `SKILL.md` — отдельный скилл.
Первая строка `SKILL.md` обязана начинаться с префикса `Description:` —
её содержимое идёт в системный промпт через `{{SKILLS_DESCRIPTION}}`.
Остальное тело отдаётся `LoadSkillTool` через `get_body(name)`.
"""

from __future__ import annotations

from pathlib import Path

_DESCRIPTION_PREFIX = "Description:"


class SkillRegistry:
    def __init__(self, skills_dir: Path | str) -> None:
        self._skills_dir = Path(skills_dir)
        self._descriptions: dict[str, str] = {}
        self._bodies: dict[str, str] = {}

    def load(self) -> None:
        """Просканировать каталог скиллов. Падает на некорректном `SKILL.md`."""
        self._descriptions.clear()
        self._bodies.clear()
        if not self._skills_dir.is_dir():
            return
        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            text = skill_md.read_text(encoding="utf-8")
            first_line, _, rest = text.partition("\n")
            stripped = first_line.strip()
            if not stripped.startswith(_DESCRIPTION_PREFIX):
                raise ValueError(
                    f"SKILL.md без 'Description:' в первой строке: {skill_md}"
                )
            description = stripped[len(_DESCRIPTION_PREFIX):].strip()
            if not description:
                raise ValueError(
                    f"Пустое описание в SKILL.md: {skill_md}"
                )
            self._descriptions[entry.name] = description
            self._bodies[entry.name] = rest.lstrip("\n")

    def list_descriptions(self) -> list[dict[str, str]]:
        """Список `[{name, description}]` в алфавитном порядке имён."""
        return [
            {"name": name, "description": self._descriptions[name]}
            for name in sorted(self._descriptions)
        ]

    def get_body(self, name: str) -> str:
        """Тело скилла без первой `Description:`-строки. `KeyError` если нет."""
        return self._bodies[name]
