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
    user_settings: Any


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
        user_settings: Any = None,
        summarizer: Any = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._tools = tools
        self._prompts = prompts
        self._skills = skills
        self._semantic_memory = semantic_memory
        self._user_settings = user_settings
        self._summarizer = summarizer

    async def run(
        self,
        *,
        goal: str,
        user_id: int,
        chat_id: int,
        conversation_id: str,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """Выполнить агентный цикл, вернуть финальный ответ для пользователя.

        Склейка `messages` — см. `_docs/memory.md` §2.4 и `_docs/agent-loop.md`
        §4. Если последний элемент `history` уже совпадает с текущим
        `user`-сообщением (`goal`), дубликат не добавляется.
        """

        chat_model = model or self._settings.ollama_default_model
        ctx = _ToolContext(
            user_id=user_id,
            chat_id=chat_id,
            conversation_id=conversation_id,
            settings=self._settings,
            llm=self._llm,
            semantic_memory=self._semantic_memory,
            skills=self._skills,
            user_settings=self._user_settings,
        )

        history_msgs = list(history or [])
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._build_system_prompt()},
            *history_msgs,
        ]
        goal_msg = {"role": "user", "content": goal}
        if not history_msgs or history_msgs[-1] != goal_msg:
            messages.append(goal_msg)

        # Проверяем размер контекста и суммаризируем если нужно
        max_context = self._settings.agent_max_context_chars
        context_size = sum(len(m.get("content", "")) for m in messages)
        if context_size > max_context and self._summarizer is not None:
            logger.info("Контекст слишком большой (%d > %d), суммаризируем историю", context_size, max_context)
            # Суммаризируем историю (кроме system prompt и текущего goal)
            history_to_summarize = history_msgs[:-1] if len(history_msgs) > 1 else history_msgs
            if history_to_summarize:
                try:
                    summary = await self._summarizer.summarize(
                        history_to_summarize,
                        model=chat_model
                    )
                    # Заменяем историю на суммаризацию
                    messages = [
                        {"role": "system", "content": self._build_system_prompt()},
                        {"role": "user", "content": f"Краткая история диалога: {summary}"},
                        goal_msg,
                    ]
                    logger.info("История суммаризирована, новый размер контекста: %d", sum(len(m.get("content", "")) for m in messages))
                except Exception as exc:
                    logger.warning("Не удалось суммаризировать историю: %s", exc)

        max_steps = self._settings.agent_max_steps
        max_chars = self._settings.agent_max_output_chars

        for step in range(1, max_steps + 1):
            response_text = await self._llm.chat(messages, model=chat_model)
            logger.info("Шаг %d: получен ответ от LLM, длина=%d", step, len(response_text))
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
                # Tool не найден или невалидные args - возвращаем observation вместо ошибки
                observation = f"Error: {exc}. Проверь список доступных tools и их аргументы."

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
