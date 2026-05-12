"""Тесты `recover_pending_journals` (спринт 06 §3.4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.dialog_journal import DialogJournal
from app.services.journal_recovery import recover_pending_journals


@pytest.fixture
async def journal(tmp_path: Path) -> DialogJournal:
    j = DialogJournal(db_path=tmp_path / "memory.db")
    await j.init()
    yield j
    await j.close()


def _make_archiver(*, side_effects: list | None = None) -> MagicMock:
    """Мок Archiver: archive — async; по умолчанию возвращает 1 чанк."""
    archiver = MagicMock()
    if side_effects is None:
        archiver.archive = AsyncMock(return_value=1)
    else:
        archiver.archive = AsyncMock(side_effect=side_effects)
    return archiver


@pytest.mark.asyncio
async def test_no_pending_returns_empty_summary(journal: DialogJournal) -> None:
    archiver = _make_archiver()
    summary = await recover_pending_journals(journal=journal, archiver=archiver)
    assert summary == {"sessions": 0, "archived": 0, "failed": 0}
    archiver.archive.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovers_pending_session_and_marks_archived(journal: DialogJournal) -> None:
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="user", kind="text", content="привет",
    )
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="assistant", kind="text", content="привет!",
    )

    archiver = _make_archiver()
    summary = await recover_pending_journals(journal=journal, archiver=archiver)

    assert summary == {"sessions": 1, "archived": 1, "failed": 0}
    archiver.archive.assert_awaited_once()
    kwargs = archiver.archive.await_args.kwargs
    assert kwargs["conversation_id"] == "c1"
    assert kwargs["user_id"] == 1
    assert kwargs["chat_id"] == 10
    assert kwargs["channel"] == "recovery"
    history = archiver.archive.await_args.args[0]
    assert [m["role"] for m in history] == ["user", "assistant"]

    # После успеха — нет висящих
    assert await journal.pending_conversations() == []


@pytest.mark.asyncio
async def test_failure_in_one_session_does_not_block_others(journal: DialogJournal) -> None:
    # Первая сессия — упадёт; вторая — пройдёт
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c1",
        role="user", kind="text", content="bad",
    )
    await journal.append(
        user_id=2, chat_id=20, conversation_id="c2",
        role="user", kind="text", content="good",
    )

    archiver = _make_archiver(side_effects=[RuntimeError("boom"), 2])
    summary = await recover_pending_journals(journal=journal, archiver=archiver)

    assert summary["sessions"] == 2
    assert summary["archived"] == 1
    assert summary["failed"] == 1

    # Сломанная c1 остаётся висеть, c2 — закрыта
    pending = await journal.pending_conversations()
    assert pending == [(1, 10, "c1")]


@pytest.mark.asyncio
async def test_empty_history_session_is_closed_without_calling_archiver(
    journal: DialogJournal,
) -> None:
    # Только системная запись с пустым content — нечего архивировать
    await journal.append(
        user_id=1, chat_id=10, conversation_id="c-sys",
        role="system", kind="system", content="   ",
    )

    archiver = _make_archiver()
    summary = await recover_pending_journals(journal=journal, archiver=archiver)

    assert summary == {"sessions": 1, "archived": 1, "failed": 0}
    archiver.archive.assert_not_awaited()
    assert await journal.pending_conversations() == []
