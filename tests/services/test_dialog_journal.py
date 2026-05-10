"""Тесты `app.services.dialog_journal.DialogJournal`."""

from __future__ import annotations

import pytest

from app.services.dialog_journal import DialogJournal


@pytest.fixture
async def journal(tmp_path):
    j = DialogJournal(db_path=tmp_path / "memory.db")
    await j.init()
    try:
        yield j
    finally:
        await j.close()


async def test_init_is_idempotent(tmp_path):
    j = DialogJournal(db_path=tmp_path / "x.db")
    await j.init()
    await j.close()
    await j.init()  # повторно — без ошибок
    await j.close()


async def test_append_and_read_roundtrip(journal):
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="user", kind="text", content="hi",
    )
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="assistant", kind="text", content="hello",
    )
    rows = await journal.read_conversation(1, "c1")
    assert len(rows) == 2
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert [r["content"] for r in rows] == ["hi", "hello"]
    assert all(r["archived_at"] is None for r in rows)


async def test_pending_lists_unarchived_only(journal):
    # сессия c1 — будет архивирована
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="user", kind="text", content="a",
    )
    # сессия c2 — останется висеть
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c2",
        role="user", kind="text", content="b",
    )
    # другая сессия другого пользователя
    await journal.append(
        user_id=2, chat_id=20, conversation_id="c3",
        role="user", kind="text", content="c",
    )

    await journal.mark_archived(1, "c1")

    pending = await journal.pending_conversations()
    keys = {(u, c) for u, _ch, c in pending}
    assert keys == {(1, "c2"), (2, "c3")}


async def test_mark_archived_returns_rowcount_and_filters_already_archived(journal):
    for content in ("a", "b", "c"):
        await journal.append(
            user_id=1, chat_id=10, conversation_id="c1",
            role="user", kind="text", content=content,
        )

    affected = await journal.mark_archived(1, "c1")
    assert affected == 3

    # повторный mark_archived ничего не трогает
    affected = await journal.mark_archived(1, "c1")
    assert affected == 0


async def test_append_supports_file_kinds(journal):
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="user", kind="document", content="goal",
        file_id="file_abc", file_path="/tmp/x.pdf",
    )
    rows = await journal.read_conversation(1, "c1")
    assert rows[0]["kind"] == "document"
    assert rows[0]["file_id"] == "file_abc"
    assert rows[0]["file_path"] == "/tmp/x.pdf"


async def test_append_rejects_invalid_role_or_kind(journal):
    with pytest.raises(ValueError):
        await journal.append(
            user_id=1, chat_id=10, conversation_id="c1",
            role="bot", kind="text", content="x",
        )
    with pytest.raises(ValueError):
        await journal.append(
            user_id=1, chat_id=10, conversation_id="c1",
            role="user", kind="audio", content="x",
        )
