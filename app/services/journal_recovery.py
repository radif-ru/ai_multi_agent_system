"""Фоновое восстановление «висящих» сессий из `dialog_journal`.

См. `_docs/memory.md` §4 и `_docs/architecture.md` §3.1. Запускается на
старте процесса параллельно с polling: для каждой сессии, в которой есть
строки с `archived_at IS NULL`, мы собираем минимальный history из журнала,
прогоняем через `Archiver.archive(...)` (тот же путь, что у `/new`),
и на успехе помечаем строки сессии archived. Ошибки изолируются на уровне
сессии — одна сломанная сессия не валит остальные и не валит бот.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.archiver import Archiver
    from app.services.dialog_journal import DialogJournal

logger = logging.getLogger(__name__)


def _entries_to_history(entries: list[dict]) -> list[dict]:
    """Преобразовать строки журнала в формат, ожидаемый `Summarizer`/`Archiver`.

    Журнал хранит per-row `role`/`kind`/`content`/`file_id`/`file_path`.
    Для архивации достаточно `{role, content}`: file-метаданные уже
    зашиты в `content` (см. handle_document/handle_voice/handle_photo).
    Пустые `content` отфильтровываются, чтобы не тратить токены.
    """
    history: list[dict] = []
    for e in entries:
        content = (e.get("content") or "").strip()
        if not content:
            continue
        role = e.get("role") or "user"
        history.append({"role": role, "content": content})
    return history


async def recover_pending_journals(
    *,
    journal: "DialogJournal",
    archiver: "Archiver",
) -> dict:
    """Архивировать все «висящие» сессии журнала.

    Возвращает сводку `{"sessions": N, "archived": K, "failed": F}`.
    Никогда не пробрасывает исключения наверх (это фоновая задача).
    """
    summary = {"sessions": 0, "archived": 0, "failed": 0}
    try:
        pending = await journal.pending_conversations()
    except Exception as exc:  # noqa: BLE001
        logger.error("journal_recovery: не удалось получить pending: %s", exc)
        return summary

    summary["sessions"] = len(pending)
    if not pending:
        logger.info("journal_recovery: нет висящих сессий")
        return summary

    logger.info("journal_recovery: найдено висящих сессий=%d", len(pending))

    for user_id, chat_id, conversation_id in pending:
        try:
            entries = await journal.read_conversation(user_id, conversation_id)
            history = _entries_to_history(entries)
            if not history:
                # Сессия из одних пустых/системных записей — просто закрываем долг.
                await journal.mark_archived(user_id, conversation_id)
                summary["archived"] += 1
                logger.info(
                    "journal_recovery: пустая сессия user=%s conv=%s — закрыта без архивации",
                    user_id, conversation_id,
                )
                continue

            chunks = await archiver.archive(
                history,
                conversation_id=conversation_id,
                user_id=user_id,
                chat_id=chat_id,
                progress_callback=None,
                user=None,
                channel="recovery",
            )
            await journal.mark_archived(user_id, conversation_id)
            summary["archived"] += 1
            logger.info(
                "journal_recovery: восстановлено user=%s conv=%s chunks=%d",
                user_id, conversation_id, chunks,
            )
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            logger.error(
                "journal_recovery: ошибка восстановления user=%s conv=%s: %s",
                user_id, conversation_id, exc,
            )

    logger.info(
        "journal_recovery: завершено sessions=%d archived=%d failed=%d",
        summary["sessions"], summary["archived"], summary["failed"],
    )
    return summary
