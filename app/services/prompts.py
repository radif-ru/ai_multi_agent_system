"""PromptLoader — загрузка системных промптов из `app/prompts/`.

См. `_docs/prompts.md` §2 (загрузка) и §3 (плейсхолдеры).

На старте процесса читает два файла:

- `Settings.agent_system_prompt_path` — главный системный промпт агентного цикла
  (содержит плейсхолдеры `{{TOOLS_DESCRIPTION}}` и `{{SKILLS_DESCRIPTION}}`).
- `app/prompts/summarizer.md` — промпт суммаризатора (фиксированный путь).
- `app/prompts/planner.md` — промпт Planner-агента (плейсхолдер `{{TASK}}`).
- `app/prompts/critic.md` — промпт Critic-агента (плейсхолдеры `{{TASK}}`, `{{PLAN}}`, `{{DRAFT}}`).

Если файла нет — `FileNotFoundError` (это явная ошибка конфигурации).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.protocol import Plan

_DEFAULT_SUMMARIZER_PATH = Path("app/prompts/summarizer.md")
_DEFAULT_PLANNER_PATH = Path("app/prompts/planner.md")
_DEFAULT_CRITIC_PATH = Path("app/prompts/critic.md")
_TOOLS_PLACEHOLDER = "{{TOOLS_DESCRIPTION}}"
_SKILLS_PLACEHOLDER = "{{SKILLS_DESCRIPTION}}"
_TASK_PLACEHOLDER = "{{TASK}}"
_PLAN_PLACEHOLDER = "{{PLAN}}"
_DRAFT_PLACEHOLDER = "{{DRAFT}}"


class PromptLoader:
    def __init__(
        self,
        agent_system_path: Path | str,
        summarizer_path: Path | str = _DEFAULT_SUMMARIZER_PATH,
        planner_path: Path | str = _DEFAULT_PLANNER_PATH,
        critic_path: Path | str = _DEFAULT_CRITIC_PATH,
    ) -> None:
        self._agent_system_template = Path(agent_system_path).read_text(
            encoding="utf-8"
        )
        self._summarizer_prompt = Path(summarizer_path).read_text(encoding="utf-8")
        self._planner_template = Path(planner_path).read_text(encoding="utf-8")
        self._critic_template = Path(critic_path).read_text(encoding="utf-8")

    @property
    def summarizer_prompt(self) -> str:
        return self._summarizer_prompt

    @property
    def agent_system_template(self) -> str:
        return self._agent_system_template

    @property
    def planner_template(self) -> str:
        return self._planner_template

    def render_agent_system(
        self, *, tools_description: str, skills_description: str
    ) -> str:
        """Подставить плейсхолдеры в шаблон главного системного промпта."""
        text = self._agent_system_template
        text = text.replace(_TOOLS_PLACEHOLDER, tools_description)
        text = text.replace(_SKILLS_PLACEHOLDER, skills_description)
        return text

    def render_planner(self, task: str) -> str:
        """Подставить задачу пользователя в шаблон Planner-промпта.

        См. `_docs/prompts.md` §3 и `app/prompts/planner.md`. Если в шаблоне
        нет плейсхолдера `{{TASK}}` — возвращаем исходный текст без ошибки
        (поведение симметрично `render_agent_system`).
        """
        return self._planner_template.replace(_TASK_PLACEHOLDER, task)

    @property
    def critic_template(self) -> str:
        return self._critic_template

    def render_critic(self, task: str, plan: "Plan", draft: str) -> str:
        """Подставить задачу, план и черновик в шаблон Critic-промпта.

        План форматируется как нумерованный список `"<id>. <description>"`,
        по одному шагу на строку — этот формат фиксирует контракт Critic'а
        (см. `app/prompts/critic.md`, секция «План Executor'а»).
        """
        plan_text = "\n".join(
            f"{step.id}. {step.description}" for step in plan.steps
        )
        text = self._critic_template
        text = text.replace(_TASK_PLACEHOLDER, task)
        text = text.replace(_PLAN_PLACEHOLDER, plan_text)
        text = text.replace(_DRAFT_PLACEHOLDER, draft)
        return text
