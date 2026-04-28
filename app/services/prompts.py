"""PromptLoader — загрузка системных промптов из `_prompts/`.

См. `_docs/prompts.md` §2 (загрузка) и §3 (плейсхолдеры).

На старте процесса читает два файла:

- `Settings.agent_system_prompt_path` — главный системный промпт агентного цикла
  (содержит плейсхолдеры `{{TOOLS_DESCRIPTION}}` и `{{SKILLS_DESCRIPTION}}`).
- `_prompts/summarizer.md` — промпт суммаризатора (фиксированный путь).

Если файла нет — `FileNotFoundError` (это явная ошибка конфигурации).
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_SUMMARIZER_PATH = Path("_prompts/summarizer.md")
_TOOLS_PLACEHOLDER = "{{TOOLS_DESCRIPTION}}"
_SKILLS_PLACEHOLDER = "{{SKILLS_DESCRIPTION}}"


class PromptLoader:
    def __init__(
        self,
        agent_system_path: Path | str,
        summarizer_path: Path | str = _DEFAULT_SUMMARIZER_PATH,
    ) -> None:
        self._agent_system_template = Path(agent_system_path).read_text(
            encoding="utf-8"
        )
        self._summarizer_prompt = Path(summarizer_path).read_text(encoding="utf-8")

    @property
    def summarizer_prompt(self) -> str:
        return self._summarizer_prompt

    @property
    def agent_system_template(self) -> str:
        return self._agent_system_template

    def render_agent_system(
        self, *, tools_description: str, skills_description: str
    ) -> str:
        """Подставить плейсхолдеры в шаблон главного системного промпта."""
        text = self._agent_system_template
        text = text.replace(_TOOLS_PLACEHOLDER, tools_description)
        text = text.replace(_SKILLS_PLACEHOLDER, skills_description)
        return text
