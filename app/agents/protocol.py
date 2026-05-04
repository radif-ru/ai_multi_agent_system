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
