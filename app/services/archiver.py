"""Архивирование сессии в долгосрочную память (`/new`).

См. `_docs/memory.md` §3.3.
"""

from __future__ import annotations

import logging
from typing import Sequence

from app.services.llm import OllamaClient
from app.services.memory import SemanticMemory
from app.services.summarizer import Summarizer

logger = logging.getLogger(__name__)


def chunk_text(text: str, *, size: int, overlap: int) -> list[str]:
    """Простое sliding-window чанкование по символам."""
    if size <= 0:
        raise ValueError("size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be in [0, size)")
    if not text:
        return []
    chunks: list[str] = []
    step = size - overlap
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i : i + size])
        if i + size >= n:
            break
        i += step
    return chunks


class Archiver:
    def __init__(
        self,
        *,
        llm: OllamaClient,
        summarizer: Summarizer,
        semantic_memory: SemanticMemory,
        summarizer_model: str,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self._llm = llm
        self._summarizer = summarizer
        self._memory = semantic_memory
        self._summarizer_model = summarizer_model
        self._embedding_model = embedding_model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def archive(
        self,
        history: Sequence[dict],
        *,
        conversation_id: str,
        user_id: int,
        chat_id: int,
    ) -> int:
        """Засуммаризовать историю и записать чанки в долгосрочную память.

        Возвращает количество записанных чанков. Если на каком-то шаге
        падает `embed`/`insert`, ранее записанные в этом вызове чанки удаляются,
        чтобы не оставлять «осиротевших» строк.
        """
        if not history:
            return 0
        summary = await self._summarizer.summarize(
            history, model=self._summarizer_model
        )
        chunks = chunk_text(
            summary, size=self._chunk_size, overlap=self._chunk_overlap
        )
        inserted_ids: list[int] = []
        try:
            for idx, chunk in enumerate(chunks):
                vector = await self._llm.embed(chunk, model=self._embedding_model)
                rowid = await self._memory.insert(
                    chunk,
                    vector,
                    {
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "conversation_id": conversation_id,
                        "chunk_index": idx,
                    },
                )
                inserted_ids.append(rowid)
        except Exception:
            for rowid in inserted_ids:
                try:
                    await self._memory.delete(rowid)
                except Exception:  # noqa: BLE001
                    logger.exception("rollback delete failed for rowid=%s", rowid)
            raise
        logger.info(
            "archive ok user_id=%s conv=%s chunks=%d",
            user_id,
            conversation_id,
            len(inserted_ids),
        )
        return len(inserted_ids)
