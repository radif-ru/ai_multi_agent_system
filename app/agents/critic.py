"""CriticAgent — валидация draft-ответа Executor'а.

См. `_board/sprints/07-multi-agent.md` §6 (Этап 3) и `_prompts/critic.md`.

Контракт: на вход — задача пользователя, план Planner'а и черновик Executor'а,
на выход — `CriticVerdict` (см. `app/agents/protocol.py`). При любой ошибке
LLM или парсинга — **fail-open**: возвращаем `CriticVerdict("PASS", "")`,
чтобы Critic не блокировал отдачу ответа пользователю (см. AC спринта 07).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.protocol import CriticVerdict, Plan, parse_critic_response
from app.services.llm import LLMBadResponse, LLMError

logger = logging.getLogger(__name__)


class CriticAgent:
    """Один LLM-вызов: (task, plan, draft) → `CriticVerdict`."""

    def __init__(self, *, llm: Any, prompts: Any, settings: Any) -> None:
        self._llm = llm
        self._prompts = prompts
        self._settings = settings

    async def review(
        self,
        task: str,
        plan: Plan,
        draft: str,
        *,
        user_id: int,
        model: str | None = None,
    ) -> CriticVerdict:
        chat_model = model or self._settings.ollama_default_model
        prompt = self._prompts.render_critic(task, plan, draft)
        messages = [{"role": "user", "content": prompt}]

        started = time.monotonic()
        try:
            response_text = await self._llm.chat(messages, model=chat_model)
        except LLMError as exc:
            self._log_fail(user_id, chat_model, started, f"llm_error:{type(exc).__name__}")
            return self._fallback()

        try:
            verdict = parse_critic_response(response_text)
        except LLMBadResponse as exc:
            self._log_fail(user_id, chat_model, started, f"parse_error:{exc}", raw=response_text)
            return self._fallback()

        self._log_ok(user_id, chat_model, started, verdict=verdict.verdict)
        return verdict

    @staticmethod
    def _fallback() -> CriticVerdict:
        return CriticVerdict(verdict="PASS", feedback="")

    @staticmethod
    def _log_ok(user_id: int, model: str, started: float, *, verdict: str) -> None:
        dur_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "critic.ok service=critic user=%s model=%s dur_ms=%d verdict=%s",
            user_id,
            model,
            dur_ms,
            verdict,
            extra={
                "service": "critic",
                "user_id": user_id,
                "model": model,
                "duration_ms": dur_ms,
                "verdict": verdict,
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
            "critic.fallback service=critic user=%s model=%s dur_ms=%d reason=%s raw=%r",
            user_id,
            model,
            dur_ms,
            reason,
            truncated,
            extra={
                "service": "critic",
                "user_id": user_id,
                "model": model,
                "duration_ms": dur_ms,
                "reason": reason,
                "status": "fallback",
            },
        )
