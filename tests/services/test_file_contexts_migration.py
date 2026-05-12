"""Тесты одноразовой миграции `data/file_contexts.db` → `dialog_journal`.

См. `app/services/file_contexts_migration.py` и задачу 06.3-bis.1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.dialog_journal import DialogJournal
from app.services.file_contexts_migration import (
    LEGACY_CONVERSATION_ID,
    migrate_file_contexts_to_journal,
)


def _make_legacy_db(path: Path, rows: list[tuple]) -> None:
    """Создать БД старого формата `file_contexts` и наполнить её."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE file_contexts (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                context TEXT NOT NULL,
                file_id TEXT,
                file_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, message_id)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO file_contexts
                (user_id, message_id, file_type, context, file_id, file_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


async def _init_journal(path: Path) -> DialogJournal:
    j = DialogJournal(db_path=path)
    await j.init()
    return j


async def test_migration_noop_when_source_absent(tmp_path):
    journal_path = tmp_path / "memory.db"
    journal = await _init_journal(journal_path)
    try:
        moved = migrate_file_contexts_to_journal(
            legacy_db_path=tmp_path / "missing.db",
            journal_db_path=journal_path,
        )
        assert moved == 0
    finally:
        await journal.close()


async def test_migration_copies_rows_and_renames_source(tmp_path):
    journal_path = tmp_path / "memory.db"
    legacy_path = tmp_path / "file_contexts.db"
    journal = await _init_journal(journal_path)
    try:
        _make_legacy_db(
            legacy_path,
            rows=[
                (7, 101, "document", "goal-1", "file_aaa", "/tmp/a.pdf"),
                (7, 102, "image", "goal-2", "file_bbb", "/tmp/b.png"),
            ],
        )
        moved = migrate_file_contexts_to_journal(
            legacy_db_path=legacy_path,
            journal_db_path=journal_path,
        )
        assert moved == 2
        # Источник переименован
        assert not legacy_path.exists()
        siblings = list(tmp_path.glob("file_contexts.db.migrated-*"))
        assert len(siblings) == 1

        rows = await journal.read_conversation(7, LEGACY_CONVERSATION_ID)
        assert {r["message_id"] for r in rows} == {101, 102}
        assert {r["kind"] for r in rows} == {"document", "image"}
        # Все строки помечены archived_at (этого долга нет)
        assert all(r["archived_at"] is not None for r in rows)
    finally:
        await journal.close()


async def test_migration_idempotent_second_run_is_noop(tmp_path):
    journal_path = tmp_path / "memory.db"
    legacy_path = tmp_path / "file_contexts.db"
    journal = await _init_journal(journal_path)
    try:
        _make_legacy_db(
            legacy_path,
            rows=[(1, 1, "document", "x", "f1", "/p/1.pdf")],
        )
        first = migrate_file_contexts_to_journal(
            legacy_db_path=legacy_path,
            journal_db_path=journal_path,
        )
        second = migrate_file_contexts_to_journal(
            legacy_db_path=legacy_path,
            journal_db_path=journal_path,
        )
        assert first == 1
        assert second == 0
    finally:
        await journal.close()
