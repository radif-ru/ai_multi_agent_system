"""Executor — единственный агент MVP.

См. `_docs/agent-loop.md` (цикл, формат ответа, защита) и
`_docs/architecture.md` §3.11.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.agents.protocol import AgentDecision, parse_agent_response
from app.services.llm import LLMBadResponse
from app.tools.errors import ArgsValidationError, ToolError, ToolNotFound

logger = logging.getLogger(__name__)


@dataclass
class _ToolContext:
    """Конкретная реализация `ToolContext`-Protocol, передаётся в tool'ы."""

    user_id: int
    chat_id: int
    conversation_id: str
    settings: Any
    llm: Any
    semantic_memory: Any
    skills: Any


class Executor:
    """Запускает цикл `thought → action → observation` для одной задачи."""

    def __init__(
        self,
        *,
        settings: Any,
        llm: Any,
        tools: Any,
        prompts: Any,
        skills: Any,
        semantic_memory: Any = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._tools = tools
        self._prompts = prompts
        self._skills = skills
        self._semantic_memory = semantic_memory

    async def run(
        self,
        *,
        goal: str,
        user_id: int,
        chat_id: int,
        conversation_id: str,
        model: str | None = None,
    ) -> str:
        """Выполнить агентный цикл, вернуть финальный ответ для пользователя."""

        chat_model = model or self._settings.ollama_default_model
        ctx = _ToolContext(
            user_id=user_id,
            chat_id=chat_id,
            conversation_id=conversation_id,
            settings=self._settings,
            llm=self._llm,
            semantic_memory=self._semantic_memory,
            skills=self._skills,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": goal},
        ]

        max_steps = self._settings.agent_max_steps
        max_chars = self._settings.agent_max_output_chars

        for step in range(1, max_steps + 1):
            response_text = await self._llm.chat(messages, model=chat_model)
            if len(response_text) > max_chars:
                self._log_parse_error(step, user_id, conversation_id, response_text)
                raise LLMBadResponse(
                    f"response too large: {len(response_text)} > {max_chars}"
                )

            try:
                parsed = parse_agent_response(response_text)
            except LLMBadResponse:
                self._log_parse_error(step, user_id, conversation_id, response_text)
                raise

            if parsed.kind == "final":
                self._log_step(step, parsed, user_id, conversation_id)
                assert parsed.final_answer is not None
                return parsed.final_answer

            self._log_step(step, parsed, user_id, conversation_id)

            assert parsed.action is not None and parsed.args is not None
            try:
                observation = await self._tools.execute(
                    parsed.action, parsed.args, ctx
                )
            except ToolError as exc:
                observation = f"Tool error: {exc}"
            except (ToolNotFound, ArgsValidationError) as exc:
                # Это ошибка модели, не tool'а: невалидный action/args.
                self._log_parse_error(step, user_id, conversation_id, response_text)
                raise LLMBadResponse(f"invalid tool call: {exc}") from exc

            messages.append({"role": "assistant", "content": response_text})
            messages.append(
                {"role": "user", "content": f"Observation: {observation}"}
            )

        self._log_max_steps(max_steps, user_id, conversation_id)
        return self._max_steps_reply(max_steps)

    def _build_system_prompt(self) -> str:
        tools_desc = _format_tools(self._tools.list_descriptions())
        skills_desc = _format_skills(self._skills.list_descriptions())
        return self._prompts.render_agent_system(
            tools_description=tools_desc,
            skills_description=skills_desc,
        )

    @staticmethod
    def _max_steps_reply(max_steps: int) -> str:
        return (
            f"Не удалось решить задачу за {max_steps} шагов. "
            "Попробуйте переформулировать запрос."
        )

    @staticmethod
    def _log_step(
        step: int,
        decision: AgentDecision,
        user_id: int,
        conversation_id: str,
    ) -> None:
        if decision.kind == "final":
            logger.info(
                "step=%d kind=final user=%s conv=%s",
                step,
                user_id,
                conversation_id,
            )
        else:
            logger.info(
                "step=%d kind=action user=%s conv=%s tool=%s",
                step,
                user_id,
                conversation_id,
                decision.action,
            )

    @staticmethod
    def _log_parse_error(
        step: int,
        user_id: int,
        conversation_id: str,
        raw: str,
    ) -> None:
        truncated = raw if len(raw) <= 500 else raw[:500] + "..."
        logger.warning(
            "step=%d kind=parse_error user=%s conv=%s raw=%r",
            step,
            user_id,
            conversation_id,
            truncated,
        )

    @staticmethod
    def _log_max_steps(max_steps: int, user_id: int, conversation_id: str) -> None:
        logger.info(
            "step=%d kind=max_steps_exceeded user=%s conv=%s reason=%r",
            max_steps,
            user_id,
            conversation_id,
            "цикл не сошёлся",
        )


def _format_tools(descriptions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for d in descriptions:
        schema = d.get("args_schema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        parts: list[str] = []
        for name, prop in props.items():
            ptype = prop.get("type", "any")
            if name in required:
                parts.append(f"{name}: {ptype}")
            else:
                default = prop.get("default")
                if default is not None:
                    parts.append(f"{name}: {ptype} = {default!r}")
                else:
                    parts.append(f"{name}?: {ptype}")
        signature = ", ".join(parts)
        lines.append(f"- {d['name']}({signature}): {d['description']}")
    return "\n".join(lines)


def _format_skills(descriptions: list[dict[str, str]]) -> str:
    if not descriptions:
        return "(нет доступных скиллов)"
    return "\n".join(f"- {d['name']}: {d['description']}" for d in descriptions)
