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
import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.services.llm import LLMBadResponse

logger = logging.getLogger(__name__)

DecisionKind = Literal["action", "final"]


def _strip_code_fence(text: str) -> str:
    """Снять markdown-fence обёртку, если она есть.

    Обрабатывает варианты:
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - с обрамляющими пробелами

    Возвращает исходный текст, если fence не найден.
    """
    stripped = text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[7:].strip()
    elif stripped.startswith("```"):
        stripped = stripped[3:].strip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()
    return stripped


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
    Толерантен к markdown-fence обёртке (```json ... ```).
    """

    text = _strip_code_fence(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        # Логируем полный raw ответ для отладки
        logger.error("Ошибка парсинга JSON. Длина raw: %d, первые 500 символов: %r", len(text), text[:500])
        # Если JSON не валидный, попробуем извлечь final_answer из текста
        # Это может случиться если модель вернула очень длинный final_answer
        if '"final_answer"' in text:
            # Попробуем извлечь значение final_answer через regex
            # Улучшенный regex который обрабатывает nested quotes и escape sequences
            import re
            # Ищем от "final_answer": до конца строки или конца JSON
            match = re.search(r'"final_answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
            if not match:
                # Если не сработало, попробуем более агрессивный подход
                match = re.search(r'"final_answer"\s*:\s*"(.+?)"\s*}', text, re.DOTALL)
            if match:
                final_answer = match.group(1)
                # Декодируем escape-последовательности
                try:
                    final_answer = json.loads(f'"{final_answer}"')
                    if isinstance(final_answer, str) and final_answer.strip():
                        logger.warning("Извлечён final_answer из повреждённого JSON")
                        return AgentDecision(kind="final", final_answer=final_answer)
                except Exception:
                    pass
        raise LLMBadResponse(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LLMBadResponse(
            f"expected JSON object, got {type(payload).__name__}"
        )

    has_final = "final_answer" in payload
    # Проверяем наличие action-полей, игнорируя null значения
    has_action_fields = any(
        k in payload and payload[k] is not None
        for k in ("thought", "action", "args")
    )

    if has_final and has_action_fields:
        raise LLMBadResponse(
            "mixed format: 'final_answer' must not coexist with thought/action/args"
        )

    if has_final:
        return _parse_final(payload)

    # Если action: null, считаем что это попытка вернуть final_answer
    if "action" in payload and payload["action"] is None:
        if "thought" in payload and payload["thought"]:
            logger.warning("LLM вернул action: null, используем thought как final_answer")
            return AgentDecision(kind="final", final_answer=payload["thought"])
        raise LLMBadResponse("action: null without thought")

    # Если есть только thought без action/args, но thought содержит final_answer - попробуем извлечь
    if "thought" in payload and "action" not in payload and "args" not in payload:
        thought = payload["thought"]
        if isinstance(thought, str) and "final_answer" in thought.lower():
            logger.warning("LLM вернул thought с final_answer без action, пробуем извлечь")
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

    # Обработка случая, когда LLM использует final_answer как действие
    if action == "final_answer":
        # Преобразуем в правильный формат final_answer
        logger.warning(
            "LLM использует final_answer как действие, преобразуем в правильный формат"
        )
        return AgentDecision(kind="final", final_answer=thought)

    return AgentDecision(kind="action", thought=thought, action=action, args=args)


# --------------------------------------------------------------------------
# Multi-agent контракты (Planner / Critic). См. _docs/multi-agent.md.
# --------------------------------------------------------------------------

# Жёсткие лимиты плана — синхронизированы с `app/prompts/planner.md`
# (см. задачу 2.1 спринта 07).
PLAN_MIN_STEPS = 1
PLAN_MAX_STEPS = 6
PLAN_STEP_DESCRIPTION_MAX_CHARS = 200

CriticVerdictLiteral = Literal["PASS", "REVISE"]


@dataclass(frozen=True)
class PlanStep:
    """Один шаг линейного плана Planner'а."""

    id: int
    description: str


@dataclass(frozen=True)
class Plan:
    """Линейный план шагов задачи (возврат Planner)."""

    steps: tuple[PlanStep, ...]


@dataclass(frozen=True)
class CriticVerdict:
    """Вердикт Critic'а по draft-ответу Executor'а."""

    verdict: CriticVerdictLiteral
    feedback: str


def parse_planner_response(text: str) -> Plan:
    """Распарсить JSON-ответ Planner'а в `Plan`.

    Толерантен к markdown-fence обёртке (```json ... ```). Любые отклонения
    от контракта нормализуются в `LLMBadResponse` (см. `_docs/multi-agent.md`).

    Ожидаемый формат:
        {"steps": [{"id": 1, "description": "..."}, {"id": 2, "description": "..."}]}
    """

    text = _strip_code_fence(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMBadResponse(f"planner: invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LLMBadResponse(
            f"planner: expected JSON object, got {type(payload).__name__}"
        )

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        raise LLMBadResponse("planner: 'steps' must be a list")
    if not (PLAN_MIN_STEPS <= len(raw_steps) <= PLAN_MAX_STEPS):
        raise LLMBadResponse(
            f"planner: 'steps' length must be in [{PLAN_MIN_STEPS}, {PLAN_MAX_STEPS}], "
            f"got {len(raw_steps)}"
        )

    steps: list[PlanStep] = []
    for idx, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            raise LLMBadResponse(
                f"planner: step #{idx} must be an object, got {type(item).__name__}"
            )
        step_id = item.get("id")
        description = item.get("description")
        if not isinstance(step_id, int) or isinstance(step_id, bool):
            raise LLMBadResponse(
                f"planner: step #{idx} 'id' must be an int, got {type(step_id).__name__}"
            )
        if not isinstance(description, str) or not description.strip():
            raise LLMBadResponse(
                f"planner: step #{idx} 'description' must be a non-empty string"
            )
        if len(description) > PLAN_STEP_DESCRIPTION_MAX_CHARS:
            raise LLMBadResponse(
                f"planner: step #{idx} 'description' exceeds "
                f"{PLAN_STEP_DESCRIPTION_MAX_CHARS} chars"
            )
        steps.append(PlanStep(id=step_id, description=description))

    return Plan(steps=tuple(steps))


def parse_critic_response(text: str) -> CriticVerdict:
    """Распарсить JSON-ответ Critic'а в `CriticVerdict`.

    Толерантен к markdown-fence. Любые отклонения от контракта — `LLMBadResponse`.

    Ожидаемый формат:
        {"verdict": "PASS"|"REVISE", "feedback": "..."}
    """

    text = _strip_code_fence(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMBadResponse(f"critic: invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LLMBadResponse(
            f"critic: expected JSON object, got {type(payload).__name__}"
        )

    verdict = payload.get("verdict")
    if not isinstance(verdict, str):
        raise LLMBadResponse("critic: 'verdict' must be a string")
    verdict_norm = verdict.strip().upper()
    if verdict_norm not in ("PASS", "REVISE"):
        raise LLMBadResponse(
            f"critic: 'verdict' must be 'PASS' or 'REVISE', got {verdict!r}"
        )

    feedback = payload.get("feedback", "")
    if feedback is None:
        feedback = ""
    if not isinstance(feedback, str):
        raise LLMBadResponse(
            f"critic: 'feedback' must be a string, got {type(feedback).__name__}"
        )

    if verdict_norm == "REVISE" and not feedback.strip():
        raise LLMBadResponse("critic: 'feedback' is required when verdict is REVISE")

    return CriticVerdict(verdict=verdict_norm, feedback=feedback)
