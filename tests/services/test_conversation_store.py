"""Тесты `app.services.conversation.ConversationStore`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.services.conversation import ConversationStore
from app.services.dialog_journal import DialogJournal


def test_add_and_get_history_independent_copy():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "hi")
    s.add_assistant_message(1, "hello")
    h = s.get_history(1)
    assert h == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    h.clear()
    h.append({"role": "user", "content": "x"})
    # Внешняя мутация копии не должна влиять на стор.
    assert len(s.get_history(1)) == 2


def test_fifo_truncation():
    s = ConversationStore(max_messages=3)
    for i in range(5):
        s.add_user_message(1, f"m{i}")
    h = s.get_history(1)
    assert [m["content"] for m in h] == ["m2", "m3", "m4"]


def test_users_are_isolated():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    s.add_user_message(2, "b")
    assert s.get_history(1) == [{"role": "user", "content": "a"}]
    assert s.get_history(2) == [{"role": "user", "content": "b"}]


def test_replace_with_summary_keeps_tail():
    s = ConversationStore(max_messages=10)
    for i in range(5):
        s.add_user_message(1, f"m{i}")
    s.replace_with_summary(1, "summary", kept_tail=2)
    h = s.get_history(1)
    assert h[0]["role"] == "system"
    assert "summary" in h[0]["content"]
    assert [m["content"] for m in h[1:]] == ["m3", "m4"]


def test_replace_with_summary_zero_tail():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    s.add_user_message(1, "b")
    s.replace_with_summary(1, "sum", kept_tail=0)
    h = s.get_history(1)
    assert len(h) == 1 and h[0]["role"] == "system"


def test_clear_removes_messages_and_conversation_id():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    cid = s.current_conversation_id(1)
    assert cid
    s.clear(1)
    assert s.get_history(1) == []
    # после clear — выдаётся новый id
    assert s.current_conversation_id(1) != cid


def test_rotate_conversation_id_returns_old_and_changes_current():
    s = ConversationStore(max_messages=10)
    cid1 = s.current_conversation_id(1)
    old = s.rotate_conversation_id(1)
    assert old == cid1
    assert s.current_conversation_id(1) != cid1


def test_rotate_when_no_prior_id_returns_empty_string():
    s = ConversationStore(max_messages=10)
    old = s.rotate_conversation_id(42)
    assert old == ""
    assert s.current_conversation_id(42)


def test_invalid_max_messages():
    with pytest.raises(ValueError):
        ConversationStore(max_messages=0)


def test_invalid_session_log_max_messages():
    with pytest.raises(ValueError):
        ConversationStore(max_messages=10, session_log_max_messages=0)


# ---- session_log (см. _docs/memory.md §2.5) ----------------------------


def test_session_log_records_user_and_assistant():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "привет, я Радиф")
    s.add_assistant_message(1, "привет, Радиф")
    log = s.get_session_log(1)
    assert log == [
        {"role": "user", "content": "привет, я Радиф"},
        {"role": "assistant", "content": "привет, Радиф"},
    ]


def test_session_log_returns_independent_copy():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    log = s.get_session_log(1)
    log.clear()
    log.append({"role": "user", "content": "x"})
    assert s.get_session_log(1) == [{"role": "user", "content": "a"}]


def test_session_log_ignores_system_messages():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    s.add_system_message(1, "tech-hint")
    s.add_assistant_message(1, "b")
    log = s.get_session_log(1)
    assert [m["role"] for m in log] == ["user", "assistant"]


def test_session_log_survives_replace_with_summary():
    """`replace_with_summary` урезает `_messages`, но НЕ полный лог сессии."""
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "привет, я Радиф")
    s.add_assistant_message(1, "привет, Радиф")
    for i in range(4):
        s.add_user_message(1, f"u{i}")
        s.add_assistant_message(1, f"a{i}")
    s.replace_with_summary(1, "summary", kept_tail=2)
    # rolling-буфер сжат
    h = s.get_history(1)
    assert h[0]["role"] == "system"
    assert "summary" in h[0]["content"]
    assert len(h) == 3
    # полный лог сохранил всё
    log = s.get_session_log(1)
    assert log[0] == {"role": "user", "content": "привет, я Радиф"}
    assert any("Радиф" in m["content"] for m in log)
    assert len(log) == 10  # 1+1 + 4*2


def test_clear_resets_session_log():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    s.add_assistant_message(1, "b")
    s.clear(1)
    assert s.get_session_log(1) == []


def test_rotate_conversation_id_resets_session_log():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "a")
    s.add_assistant_message(1, "b")
    s.rotate_conversation_id(1)
    assert s.get_session_log(1) == []


def test_session_log_users_are_isolated():
    s = ConversationStore(max_messages=10)
    s.add_user_message(1, "u1")
    s.add_user_message(2, "u2")
    s.clear(1)
    assert s.get_session_log(1) == []
    assert s.get_session_log(2) == [{"role": "user", "content": "u2"}]


# ---- file context backed by dialog_journal (см. _docs/memory.md §2.6) ----


async def test_get_file_context_reads_from_dialog_journal(tmp_path: Path) -> None:
    """`get_file_context` восстанавливает goal по `message_id` из dialog_journal."""
    db_path = tmp_path / "memory.db"
    journal = DialogJournal(db_path=db_path)
    await journal.init()
    try:
        await journal.append(
            user_id=42, chat_id=42, conversation_id="cid-1",
            role="user", kind="document",
            content="Документ user=42 msg=7",
            file_id="file_abc", file_path="/tmp/a.pdf",
            message_id=7,
        )
    finally:
        await journal.close()

    s = ConversationStore(max_messages=10, journal_db_path=db_path)
    assert s.get_file_context(42, 7) == "Документ user=42 msg=7"
    # Повторный вызов попадает в in-memory кеш.
    assert s.get_file_context(42, 7) == "Документ user=42 msg=7"


async def test_get_file_context_returns_none_when_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    journal = DialogJournal(db_path=db_path)
    await journal.init()
    await journal.close()
    s = ConversationStore(max_messages=10, journal_db_path=db_path)
    assert s.get_file_context(42, 999) is None


def test_get_file_context_without_db_path_returns_none() -> None:
    s = ConversationStore(max_messages=10)
    assert s.get_file_context(1, 1) is None


def test_save_file_context_removed() -> None:
    """`save_file_context` удалён — данные пишутся через подписчик dialog_journal."""
    s = ConversationStore(max_messages=10)
    assert not hasattr(s, "save_file_context")


def test_conversation_store_does_not_create_file_contexts_db(tmp_path: Path) -> None:
    """ConversationStore больше не открывает `data/file_contexts.db`."""
    ConversationStore(
        max_messages=10, journal_db_path=tmp_path / "memory.db",
    )
    # Файл `file_contexts.db` не должен появиться рядом.
    assert not (tmp_path / "file_contexts.db").exists()
    # И никаких таблиц `file_contexts` в memory.db быть не должно (init dialog_journal
    # делается отдельно через DialogJournal.init()).
    if (tmp_path / "memory.db").exists():
        with sqlite3.connect(tmp_path / "memory.db") as conn:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "file_contexts" not in tables


def test_session_log_overflow_drops_head_and_warns(caplog):
    s = ConversationStore(max_messages=100, session_log_max_messages=3)
    with caplog.at_level("WARNING", logger="app.services.conversation"):
        s.add_user_message(1, "m0")
        s.add_assistant_message(1, "m1")
        s.add_user_message(1, "m2")
        s.add_assistant_message(1, "m3")
    log = s.get_session_log(1)
    assert [m["content"] for m in log] == ["m1", "m2", "m3"]
    assert any("session_log overflow" in rec.message for rec in caplog.records)
