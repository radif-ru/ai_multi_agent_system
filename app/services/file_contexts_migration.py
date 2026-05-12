"""Одноразовая миграция `data/file_contexts.db` → `dialog_journal`.

Контекст: до этапа 06.3-bis в проекте параллельно жили две SQLite-таблицы
с одинаковым по сути содержимым: `file_contexts` в `data/file_contexts.db`
(PK `(user_id, message_id)`) и `dialog_journal` в `data/memory.db`. Этап
3-bis сводит их в одну: `dialog_journal` расширяется колонкой `message_id`,
а старая БД мигрируется один раз и переименовывается в
`data/file_contexts.db.migrated-<ts>` (резервная копия — удалит пользователь
руками, см. `_docs/memory.md` §2.6).

Алгоритм идемпотентный: если файл-источника нет — функция тихо выходит.
После успешной миграции файл переименовывается, поэтому повторный запуск
ничего не делает. При ошибке чтения файла источник остаётся на месте
(переименование — только после успешного `commit`).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# Имя «спец-сессии» для строк, у которых исторически нет `conversation_id`
# (старая таблица его не хранила). Используется только как заглушка, чтобы
# не нарушать NOT NULL и не путать со строками реальных сессий журнала.
LEGACY_CONVERSATION_ID = "legacy"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate_file_contexts_to_journal(
    *,
    legacy_db_path: Path,
    journal_db_path: Path,
) -> int:
    """Перенести строки из старого `file_contexts.db` в `dialog_journal`.

    Returns:
        Количество перенесённых строк. `0`, если файл-источник отсутствует
        или таблица пуста / повреждена.
    """
    if not legacy_db_path.exists():
        return 0
    if not journal_db_path.exists():
        # `DialogJournal.init()` создаёт файл — если его нет, ничего не делаем
        # (значит, журнал ещё не инициализирован, пусть вызывающий это исправит).
        logger.warning(
            "file_contexts_migration: journal не инициализирован (%s), пропускаем",
            journal_db_path,
        )
        return 0

    moved = 0
    src = sqlite3.connect(legacy_db_path)
    dst = sqlite3.connect(journal_db_path)
    try:
        try:
            rows = src.execute(
                """
                SELECT user_id, message_id, file_type, context, file_id, file_path,
                       created_at
                FROM file_contexts
                """
            ).fetchall()
        except sqlite3.OperationalError as exc:
            # Старая БД без таблицы / повреждена — выходим без переименования.
            logger.info(
                "file_contexts_migration: исходная таблица недоступна (%s), пропускаем",
                exc,
            )
            return 0

        now = _now_iso()
        for row in rows:
            user_id, message_id, file_type, context, file_id, file_path, created_at = row
            kind = file_type if file_type in ("text", "document", "voice", "image", "system") else "document"
            dst.execute(
                """
                INSERT INTO dialog_journal
                    (user_id, chat_id, conversation_id, role, kind, content,
                     file_id, file_path, created_at, archived_at, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    int(user_id),
                    # Старый чат-id не знаем — кладём user_id как разумный дефолт
                    # (для одиночных чатов Telegram это и так совпадает).
                    int(user_id),
                    LEGACY_CONVERSATION_ID,
                    "user",
                    kind,
                    context or "",
                    file_id,
                    file_path,
                    created_at or now,
                    now,  # archived_at — сразу закрываем, эти строки не подлежат
                    # фоновому восстановлению.
                    int(message_id) if message_id is not None else None,
                ),
            )
            moved += 1
        dst.commit()
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()

    # Переименовываем исходник — повторный запуск не подхватит его.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = legacy_db_path.with_name(f"{legacy_db_path.name}.migrated-{ts}")
    legacy_db_path.rename(target)
    logger.info(
        "file_contexts_migration: перенесено %d строк, источник переименован в %s",
        moved, target,
    )
    return moved
