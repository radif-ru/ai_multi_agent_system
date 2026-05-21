"""PlannerAgent — декомпозиция задачи в линейный план.

См. `_board/sprints/07-multi-agent.md` §5 (Этап 2) и `app/prompts/planner.md`.

Контракт: на вход — текст задачи пользователя, на выход — `Plan` (см.
`app/agents/protocol.py`). При любой ошибке LLM или парсинга — возвращаем
fallback-план из одного шага, повторяющего исходную задачу. Этот fallback
позволяет оркестратору безопасно деградировать до single-step Executor'а
(см. AC спринта 07).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.protocol import Plan, PlanStep, parse_planner_response
from app.services.llm import LLMBadResponse, LLMError

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Один LLM-вызов: задача → `Plan`."""

    def __init__(self, *, llm: Any, prompts: Any, settings: Any) -> None:
        self._llm = llm
        self._prompts = prompts
        self._settings = settings

    async def plan(
        self,
        task: str,
        *,
        user_id: int,
        model: str | None = None,
    ) -> Plan:
        chat_model = model or self._settings.ollama_default_model
        prompt = self._prompts.render_planner(task)
        messages = [{"role": "user", "content": prompt}]

        started = time.monotonic()
        try:
            response_text = await self._llm.chat(messages, model=chat_model)
        except LLMError as exc:
            self._log_fail(user_id, chat_model, started, f"llm_error:{type(exc).__name__}")
            return self._fallback(task)

        try:
            plan = parse_planner_response(response_text)
        except LLMBadResponse as exc:
            self._log_fail(user_id, chat_model, started, f"parse_error:{exc}", raw=response_text)
            return self._fallback(task)

        self._log_ok(user_id, chat_model, started, steps_count=len(plan.steps))
        return plan

    @staticmethod
    def _fallback(task: str) -> Plan:
        return Plan(steps=(PlanStep(id=1, description=task[:200]),))

    @staticmethod
    def _log_ok(user_id: int, model: str, started: float, *, steps_count: int) -> None:
        dur_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "planner.ok service=planner user=%s model=%s dur_ms=%d steps=%d",
            user_id,
            model,
            dur_ms,
            steps_count,
            extra={
                "service": "planner",
                "user_id": user_id,
                "model": model,
                "duration_ms": dur_ms,
                "steps_count": steps_count,
                "status": "ok",
            },
        )

    @staticmethod
    def _log_fail(
        user_id: int,
        model: str,
        started: float,
        reason: str,
        *,
        raw: str | None = None,
    ) -> None:
        dur_ms = int((time.monotonic() - started) * 1000)
        truncated = None
        if raw is not None:
            truncated = raw if len(raw) <= 500 else raw[:500] + "..."
        logger.warning(
            "planner.fallback service=planner user=%s model=%s dur_ms=%d reason=%s raw=%r",
            user_id,
            model,
            dur_ms,
            reason,
            truncated,
            extra={
                "service": "planner",
                "user_id": user_id,
                "model": model,
                "duration_ms": dur_ms,
                "reason": reason,
                "status": "fallback",
            },
        )
