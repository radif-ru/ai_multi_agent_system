"""Архивирование сессии в долгосрочную память (`/new`).

См. `_docs/memory.md` §3.3.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Awaitable, Callable, Sequence

from app.services.llm import OllamaClient
from app.services.memory import SemanticMemory
from app.services.summarizer import Summarizer

if TYPE_CHECKING:
    from app.core.events import EventBus
    from app.users.models import User

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
        concurrency_limit: int = 5,
        event_bus: "EventBus | None" = None,
    ) -> None:
        self._llm = llm
        self._summarizer = summarizer
        self._memory = semantic_memory
        self._summarizer_model = summarizer_model
        self._embedding_model = embedding_model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._concurrency_limit = concurrency_limit
        self._event_bus = event_bus

    async def archive(
        self,
        history: Sequence[dict],
        *,
        conversation_id: str,
        user_id: int,
        chat_id: int,
        progress_callback: Callable[[str], Awaitable[None] | None] | None = None,
        user: "User | None" = None,
        channel: str | None = None,
    ) -> int:
        """Засуммаризовать историю и записать чанки в долгосрочную память.

        Возвращает количество записанных чанков. Если на каком-то шаге
        падает `embed`/`insert`, ранее записанные в этом вызове чанки удаляются,
        чтобы не оставлять «осиротевших» строк.

        Args:
            progress_callback: функция обратного вызова для уведомления о прогрессе
                              (может быть sync или async)
        """
        async def _notify(text: str) -> None:
            if progress_callback is not None:
                result = progress_callback(text)
                if asyncio.iscoroutine(result):
                    await result
        if not history:
            return 0

        total_start = time.monotonic()

        # Этап 1: Суммаризация
        await _notify("Суммирую историю диалога...")
        sum_start = time.monotonic()
        summary = await self._summarizer.summarize(
            history, model=self._summarizer_model
        )
        sum_dur = time.monotonic() - sum_start
        logger.info("archive stage=summarize dur_ms=%d", int(sum_dur * 1000))

        # Этап 2: Чанкинг
        chunk_start = time.monotonic()
        chunks = chunk_text(
            summary, size=self._chunk_size, overlap=self._chunk_overlap
        )
        chunk_dur = time.monotonic() - chunk_start
        logger.info("archive stage=chunking chunks=%d dur_ms=%d", len(chunks), int(chunk_dur * 1000))

        if not chunks:
            return 0

        # Этап 3: Параллельный embedding
        await _notify(f"Создаю эмбеддинги для {len(chunks)} чанков...")
        embed_start = time.monotonic()

        semaphore = asyncio.Semaphore(self._concurrency_limit)

        async def _embed_one(idx: int, text: str) -> tuple[int, list[float]]:
            async with semaphore:
                vector = await self._llm.embed(text, model=self._embedding_model)
                return idx, vector

        embed_tasks = [_embed_one(i, chunk) for i, chunk in enumerate(chunks)]
        embed_results = await asyncio.gather(*embed_tasks, return_exceptions=True)

        # Проверяем ошибки
        vectors: list[tuple[int, list[float]]] = []
        for result in embed_results:
            if isinstance(result, Exception):
                raise result
            vectors.append(result)

        embed_dur = time.monotonic() - embed_start
        logger.info("archive stage=embedding chunks=%d dur_ms=%d", len(chunks), int(embed_dur * 1000))

        # Этап 4: Запись в БД
        await _notify("Сохраняю в память...")
        db_start = time.monotonic()

        inserted_ids: list[int] = []
        try:
            for idx, vector in vectors:
                rowid = await self._memory.insert(
                    chunks[idx],
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
                    logger.exception("откат: не удалось удалить chunk rowid=%s", rowid)
            raise

        db_dur = time.monotonic() - db_start
        total_dur = time.monotonic() - total_start

        logger.info(
            "archive stage=database chunks=%d dur_ms=%d",
            len(inserted_ids), int(db_dur * 1000)
        )
        logger.info(
            "archive ok user_id=%s conv=%s chunks=%d total_dur_ms=%d",
            user_id,
            conversation_id,
            len(inserted_ids),
            int(total_dur * 1000),
        )

        # Публикуем событие ConversationArchived при успешном архивировании
        if self._event_bus is not None and user is not None and channel is not None:
            from app.core.events import ConversationArchived

            await self._event_bus.publish(
                ConversationArchived(
                    user=user,
                    conversation_id=conversation_id,
                    chunks=len(inserted_ids),
                    channel=channel,
                )
            )

        return len(inserted_ids)
