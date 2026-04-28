"""Суммаризатор истории диалога.

Тонкая обёртка над `OllamaClient.chat`. См. `_docs/architecture.md` §3.5
и `_docs/memory.md` §3.3 (map-reduce режим для длинных логов).
"""

from __future__ import annotations

import json
import logging
from typing import Sequence

from app.services.llm import OllamaClient

logger = logging.getLogger(__name__)


class Summarizer:
    """Суммаризатор истории.

    Для коротких логов делает один проход (`chat`). Если число сообщений
    превышает ``chunk_messages`` — переходит в map-reduce: режет лог на
    батчи, суммаризует каждый отдельно (map), затем сводит мини-саммари
    в финальное (reduce). Это позволяет работать с длинными сессиями,
    не упираясь в контекст модели и не теряя ранние факты.
    """

    def __init__(
        self,
        *,
        llm: OllamaClient,
        system_prompt: str,
        chunk_messages: int = 30,
    ) -> None:
        if chunk_messages <= 0:
            raise ValueError("chunk_messages must be > 0")
        self._llm = llm
        self._system_prompt = system_prompt
        self._chunk_messages = chunk_messages

    async def summarize(
        self,
        messages: Sequence[dict],
        *,
        model: str,
        temperature: float = 0.0,
    ) -> str:
        """Вернуть краткое резюме истории; LLMError пробрасывается без глушения.

        Если ``len(messages) <= chunk_messages`` — один вызов `llm.chat`.
        Иначе map-reduce: ``ceil(N / chunk_messages) + 1`` вызовов.
        """
        msgs = list(messages)
        if len(msgs) <= self._chunk_messages:
            return await self._summarize_chat(msgs, model=model, temperature=temperature)

        # map: суммаризуем каждый батч отдельно
        batch_summaries: list[str] = []
        for i in range(0, len(msgs), self._chunk_messages):
            batch = msgs[i : i + self._chunk_messages]
            logger.info(
                "summarize map batch %d/%d size=%d",
                i // self._chunk_messages + 1,
                (len(msgs) + self._chunk_messages - 1) // self._chunk_messages,
                len(batch),
            )
            batch_summary = await self._summarize_chat(
                batch, model=model, temperature=temperature
            )
            batch_summaries.append(batch_summary)

        # reduce: сводим мини-саммари в одно
        reduce_payload = [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    "Сведи следующие частичные резюме одного длинного "
                    "диалога в одно итоговое резюме по тем же правилам. "
                    "Сохрани все конкретные факты о пользователе (имена, "
                    "числа, даты, договорённости). Частичные резюме:\n\n"
                    + "\n\n---\n\n".join(
                        f"[часть {i + 1}]\n{s}" for i, s in enumerate(batch_summaries)
                    )
                ),
            },
        ]
        logger.info("summarize reduce parts=%d", len(batch_summaries))
        return await self._llm.chat(
            reduce_payload, model=model, temperature=temperature
        )

    async def _summarize_chat(
        self,
        messages: Sequence[dict],
        *,
        model: str,
        temperature: float,
    ) -> str:
        payload = [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    "Резюмируй следующий диалог:\n"
                    + json.dumps(list(messages), ensure_ascii=False)
                ),
            },
        ]
        return await self._llm.chat(payload, model=model, temperature=temperature)
