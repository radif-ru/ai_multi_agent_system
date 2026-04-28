"""Контракт ответа модели в агентном цикле.

См. `_docs/agent-loop.md` §2 и `_docs/testing.md` §3.3.

Модель в каждом шаге обязана вернуть ровно один JSON-объект одного из двух
видов: «шаг с действием» (`thought` + `action` + `args`) или «финальный
ответ» (`final_answer`). Любое нарушение формата → `LLMBadResponse`.

Проверка существования tool по имени и валидация `args` по схеме —
ответственность вызывающего кода (`Executor` через `ToolRegistry`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from app.services.llm import LLMBadResponse

DecisionKind = Literal["action", "final"]


@dataclass(frozen=True)
class AgentDecision:
    """Распарсенное решение агента на одном шаге цикла."""

    kind: DecisionKind
    thought: str | None = None
    action: str | None = None
    args: dict[str, Any] | None = None
    final_answer: str | None = None


def parse_agent_response(text: str) -> AgentDecision:
    """Распарсить JSON-ответ модели в `AgentDecision`.

    Все ошибки формата нормализуются в `LLMBadResponse`.
    """

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMBadResponse(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LLMBadResponse(
            f"expected JSON object, got {type(payload).__name__}"
        )

    has_final = "final_answer" in payload
    has_action_fields = any(k in payload for k in ("thought", "action", "args"))

    if has_final and has_action_fields:
        raise LLMBadResponse(
            "mixed format: 'final_answer' must not coexist with thought/action/args"
        )

    if has_final:
        return _parse_final(payload)
    return _parse_action(payload)


def _parse_final(payload: dict[str, Any]) -> AgentDecision:
    final_answer = payload.get("final_answer")
    if not isinstance(final_answer, str) or not final_answer.strip():
        raise LLMBadResponse("'final_answer' must be a non-empty string")
    return AgentDecision(kind="final", final_answer=final_answer)


def _parse_action(payload: dict[str, Any]) -> AgentDecision:
    if "thought" not in payload:
        raise LLMBadResponse("missing required field: 'thought'")
    if "action" not in payload:
        raise LLMBadResponse("missing required field: 'action'")
    if "args" not in payload:
        raise LLMBadResponse("missing required field: 'args'")

    thought = payload["thought"]
    action = payload["action"]
    args = payload["args"]

    if not isinstance(thought, str) or not thought.strip():
        raise LLMBadResponse("'thought' must be a non-empty string")
    if not isinstance(action, str) or not action.strip():
        raise LLMBadResponse("'action' must be a non-empty string")
    if not isinstance(args, dict):
        raise LLMBadResponse(
            f"'args' must be an object, got {type(args).__name__}"
        )

    return AgentDecision(kind="action", thought=thought, action=action, args=args)
