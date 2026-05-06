"""Tool `load_skill` — загрузка тела скилла из `_skills/`.

См. `_docs/tools.md` §4.6 и `_docs/skills.md` §4.

Этот tool полагается на `ctx.skills.get_body(name)` (`SkillRegistry`,
Задача 4.1). Tool оборачивает `KeyError`/`SkillNotFound` в `ToolError`.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError


class LoadSkillTool(Tool):
    name = "load_skill"
    description = (
        "Загрузить полный текст скилла по имени из `_skills/` "
        "(без первой строки `Description:`)."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def __init__(self, *, max_output_chars: int = 50000) -> None:
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        name = str(args["name"]).strip()
        if not name:
            raise ToolError("empty skill name")
        try:
            body = ctx.skills.get_body(name)
        except KeyError as exc:
            raise ToolError(f"skill not found: {name}") from exc
        if not isinstance(body, str):
            body = str(body)
        return truncate_output(body, self._max_output_chars)
