"""Авто-подгрузка архива в первый ход новой сессии.

См. `_docs/memory.md` §3.6 и `_docs/architecture.md` §3.10.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

BOOTSTRAP_HEADER = (
    "Контекст из прошлых сессий пользователя (используй только если он "
    "действительно относится к текущему запросу):"
)


async def build_bootstrap_message(
    *,
    query: str,
    user_id: int,
    settings: Any,
    llm: Any,
    semantic_memory: Any,
) -> dict[str, str] | None:
    """Собрать system-message с релевантным контекстом из архива или вернуть None.

    Возвращает None, если: фича выключена, `SemanticMemory` или `OllamaClient`
    не переданы, в архиве ничего не нашлось или `embed` / `search` упали.
    Падения логируются на уровне WARNING; основной ход вызывающей стороны
    не должен страдать.
    """

    if not getattr(settings, "session_bootstrap_enabled", False):
        return None
    if semantic_memory is None or llm is None:
        return None
    top_k = int(getattr(settings, "session_bootstrap_top_k", 0))
    if top_k <= 0:
        return None

    try:
        embedding = await llm.embed(query, model=settings.embedding_model)
        rows = await semantic_memory.search(
            embedding, top_k=top_k, scope_user_id=user_id
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "session_bootstrap failed user=%s", user_id, exc_info=True
        )
        return None

    if not rows:
        return None

    bullets = "\n".join(f"- {row['text']}" for row in rows)
    return {
        "role": "system",
        "content": f"{BOOTSTRAP_HEADER}\n\n{bullets}",
    }
