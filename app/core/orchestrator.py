"""Core / Orchestrator — единственная точка входа от любого адаптера.

См. `_docs/architecture.md` §3.10–§3.11 и `_docs/multi-agent.md`. Контракт
`handle_user_task(text, user_id, chat_id)` стабилен для адаптеров; внутри
скрыта одна из трёх схем (`AGENT_REFLECTION_MODE`):

- `OFF` — Executor напрямую (поведение MVP);
- `NORMAL` — Planner → Executor → Critic (один проход);
- `DEEP` — то же, но Critic итерируется до `AGENT_REFLECTION_MAX_ITERATIONS`.

Любая ошибка Planner/Critic → graceful degradation: возвращаем последний
известный draft Executor'а (см. AC спринта 07).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.session_bootstrap import build_bootstrap_message

if TYPE_CHECKING:
    from app.agents.critic import CriticAgent
    from app.agents.executor import Executor
    from app.agents.planner import PlannerAgent
    from app.agents.protocol import Plan
    from app.config import Settings
    from app.services.conversation import ConversationStore
    from app.services.llm import OllamaClient
    from app.services.memory import SemanticMemory
    from app.services.model_registry import UserSettingsRegistry

logger = logging.getLogger(__name__)


async def handle_user_task(
    text: str,
    *,
    user_id: int,
    chat_id: int,
    conversations: "ConversationStore",
    executor: "Executor",
    model: str | None = None,
    settings: "Settings | None" = None,
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
    planner: "PlannerAgent | None" = None,
    critic: "CriticAgent | None" = None,
    user_settings: "UserSettingsRegistry | None" = None,
) -> str:
    """Запустить агентный цикл и вернуть финальный текст для пользователя.

    Args:
        text: формулировка задачи пользователя.
        user_id: Telegram user_id (или эквивалент в другом адаптере).
        chat_id: Telegram chat_id.
        conversations: in-memory история диалога (источник `conversation_id`).
        executor: настроенный экземпляр `Executor`.
        model: per-user override модели; `None` → default из `Settings`.
        settings: `Settings`; нужен для авто-подгрузки архива и режима рефлексии.
        llm: `OllamaClient` — для embed запроса при авто-подгрузке.
        semantic_memory: `SemanticMemory` — для поиска по архиву.
        planner: `PlannerAgent`; обязателен для NORMAL/DEEP, иначе режим даунгрейдится в OFF.
        critic: `CriticAgent`; обязателен для NORMAL/DEEP, иначе режим даунгрейдится в OFF.
        user_settings: `UserSettingsRegistry` для per-user override режима рефлексии.
    """

    conversation_id = conversations.current_conversation_id(user_id)
    history = conversations.get_history(user_id)
    if len(history) == 1 and settings is not None:
        bootstrap = await build_bootstrap_message(
            query=text,
            user_id=user_id,
            settings=settings,
            llm=llm,
            semantic_memory=semantic_memory,
        )
        if bootstrap is not None:
            history = [bootstrap, *history]

    mode = _resolve_mode(user_id, settings=settings, user_settings=user_settings)
    if mode == "OFF" or planner is None or critic is None:
        logger.info(
            "orchestrator.mode mode=OFF user=%s",
            user_id,
            extra={"service": "orchestrator", "mode": "OFF", "user_id": user_id},
        )
        return await executor.run(
            goal=text,
            user_id=user_id,
            chat_id=chat_id,
            conversation_id=conversation_id,
            model=model,
            history=history,
        )

    logger.info(
        "orchestrator.mode mode=%s user=%s",
        mode,
        user_id,
        extra={"service": "orchestrator", "mode": mode, "user_id": user_id},
    )

    try:
        plan = await planner.plan(text, user_id=user_id, model=model)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "orchestrator.planner_fallback user=%s err=%s",
            user_id, exc,
            extra={"service": "orchestrator", "user_id": user_id},
        )
        return await executor.run(
            goal=text,
            user_id=user_id,
            chat_id=chat_id,
            conversation_id=conversation_id,
            model=model,
            history=history,
        )
    logger.info(
        "orchestrator.planner_ok user=%s steps=%d",
        user_id,
        len(plan.steps),
        extra={
            "service": "orchestrator",
            "user_id": user_id,
            "steps_count": len(plan.steps),
        },
    )

    augmented_goal = _augment_goal_with_plan(text, plan)
    draft = await executor.run(
        goal=augmented_goal,
        user_id=user_id,
        chat_id=chat_id,
        conversation_id=conversation_id,
        model=model,
        history=history,
    )

    max_iter = 1
    if mode == "DEEP" and settings is not None:
        max_iter = settings.agent_reflection_max_iterations

    for iteration in range(1, max_iter + 1):
        try:
            verdict = await critic.review(text, plan, draft, user_id=user_id, model=model)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "orchestrator.critic_error user=%s iter=%d err=%s",
                user_id, iteration, exc,
                extra={"service": "orchestrator", "user_id": user_id, "iteration": iteration},
            )
            return draft

        logger.info(
            "orchestrator.iteration user=%s iter=%d verdict=%s",
            user_id, iteration, verdict.verdict,
            extra={
                "service": "orchestrator",
                "user_id": user_id,
                "iteration": iteration,
                "verdict": verdict.verdict,
            },
        )

        if verdict.verdict == "PASS":
            return draft

        revise_goal = (
            f"Исходная задача: {text}\n"
            f"Черновик: {draft}\n"
            f"Замечания: {verdict.feedback}\n"
            "Исправь ответ."
        )
        try:
            draft = await executor.run(
                goal=revise_goal,
                user_id=user_id,
                chat_id=chat_id,
                conversation_id=conversation_id,
                model=model,
                history=history,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "orchestrator.revise_error user=%s iter=%d err=%s",
                user_id, iteration, exc,
                extra={"service": "orchestrator", "user_id": user_id, "iteration": iteration},
            )
            return draft

    return draft


def _resolve_mode(
    user_id: int,
    *,
    settings: "Settings | None",
    user_settings: "UserSettingsRegistry | None",
) -> str:
    if user_settings is not None:
        per_user = user_settings.get_reflection_mode(user_id)
        if per_user:
            return per_user
    if settings is not None:
        return getattr(settings, "agent_reflection_mode", "OFF")
    return "OFF"


def _augment_goal_with_plan(text: str, plan: "Plan") -> str:
    plan_text = "\n".join(f"{s.id}) {s.description}" for s in plan.steps)
    return f"{text}\n\nПлан выполнения:\n{plan_text}"
