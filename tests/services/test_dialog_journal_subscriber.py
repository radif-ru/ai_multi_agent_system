"""Тесты подписчиков dialog_journal."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.events import MessageReceived, ResponseGenerated
from app.services.conversation import ConversationStore
from app.services.dialog_journal import DialogJournal
from app.services.dialog_journal_subscriber import (
    on_message_received_journal,
    on_response_generated_journal,
)
from app.users.models import User


@pytest.fixture
async def journal(tmp_path):
    j = DialogJournal(db_path=tmp_path / "memory.db")
    await j.init()
    try:
        yield j
    finally:
        await j.close()


@pytest.fixture
def conversations(tmp_path):
    return ConversationStore(
        max_messages=10, file_contexts_db=tmp_path / "file_contexts.db",
    )


def _user(uid: int = 42) -> User:
    return User(
        id=uid, channel="telegram", external_id=str(uid),
        display_name="Test", created_at=datetime(2026, 5, 10),
    )


async def test_on_message_received_writes_user_text_with_internal_cid(
    journal, conversations
):
    user = _user(42)
    cid = conversations.current_conversation_id(42)

    event = MessageReceived(
        user=user, text="hi", conversation_id="100",  # 100 = chat_id
        channel="telegram",
    )
    await on_message_received_journal(
        event, conversations=conversations, journal=journal
    )

    rows = await journal.read_conversation(42, cid)
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["kind"] == "text"
    assert rows[0]["content"] == "hi"


async def test_on_response_generated_writes_assistant_text(journal, conversations):
    user = _user(42)
    cid = conversations.current_conversation_id(42)

    event = ResponseGenerated(
        user=user, text="hello", conversation_id="100", channel="telegram",
    )
    await on_response_generated_journal(
        event, conversations=conversations, journal=journal
    )

    rows = await journal.read_conversation(42, cid)
    assert len(rows) == 1
    assert rows[0]["role"] == "assistant"
    assert rows[0]["content"] == "hello"


async def test_subscribers_swallow_journal_errors(conversations, caplog):
    """Падение журнала не должно ломать подписчик."""

    class BrokenJournal:
        async def append(self, **kwargs):
            raise RuntimeError("disk full")

    user = _user(42)
    event = MessageReceived(
        user=user, text="x", conversation_id="100", channel="telegram",
    )

    # Не должно бросить
    await on_message_received_journal(
        event, conversations=conversations, journal=BrokenJournal(),
    )
    assert any("dialog_journal" in r.message for r in caplog.records)
