"""Суммаризатор истории диалога.

Тонкая обёртка над `OllamaClient.chat`. См. `_docs/architecture.md` §3.5.
"""

from __future__ import annotations

import json
import logging
from typing import Sequence

from app.services.llm import OllamaClient

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, *, llm: OllamaClient, system_prompt: str) -> None:
        self._llm = llm
        self._system_prompt = system_prompt

    async def summarize(
        self,
        messages: Sequence[dict],
        *,
        model: str,
        temperature: float = 0.0,
    ) -> str:
        """Вернуть краткое резюме истории; LLMError пробрасывается без глушения."""
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
