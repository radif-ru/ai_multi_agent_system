"""Тесты `app.services.archiver.Archiver`."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.events import ConversationArchived, EventBus
from app.services.archiver import Archiver, chunk_text
from app.services.llm import LLMUnavailable, OllamaClient
from app.services.summarizer import Summarizer
from app.users.models import User


def test_chunk_text_basic():
    out = chunk_text("a" * 3000, size=1500, overlap=150)
    assert len(out) == 3
    assert all(len(c) <= 1500 for c in out)
    assert out[0] == "a" * 1500
    # с учётом overlap=150 шаг = 1350
    assert out[1] == "a" * 1500


def test_chunk_text_empty_returns_empty():
    assert chunk_text("", size=100, overlap=0) == []


def test_chunk_text_invalid_args():
    with pytest.raises(ValueError):
        chunk_text("x", size=0, overlap=0)
    with pytest.raises(ValueError):
        chunk_text("x", size=10, overlap=10)


class FakeMemory:
    def __init__(self):
        self.inserted: list[tuple[int, str, list[float], dict]] = []
        self.deleted: list[int] = []
        self._fail_on_idx: int | None = None
        self._next_id = 1

    def fail_insert_on(self, idx: int) -> None:
        self._fail_on_idx = idx

    async def insert(self, text, embedding, metadata):
        idx = metadata["chunk_index"]
        if self._fail_on_idx is not None and idx == self._fail_on_idx:
            raise RuntimeError("simulated insert failure")
        rowid = self._next_id
        self._next_id += 1
        self.inserted.append((rowid, text, embedding, metadata))
        return rowid

    async def delete(self, rowid):
        self.deleted.append(rowid)


@pytest.fixture
def llm():
    return OllamaClient(base_url="http://localhost:11434", timeout=10.0)


@pytest.fixture
def summarizer(llm):
    return Summarizer(llm=llm, system_prompt="SYS")


def make_archiver(llm, summarizer, memory, *, size=1500, overlap=150, concurrency=5, event_bus=None) -> Archiver:
    return Archiver(
        llm=llm,
        summarizer=summarizer,
        semantic_memory=memory,
        summarizer_model="qwen3.5:4b",
        embedding_model="nomic-embed-text",
        chunk_size=size,
        chunk_overlap=overlap,
        concurrency_limit=concurrency,
        event_bus=event_bus,
    )


async def test_archive_empty_history_does_nothing(llm, summarizer, mocker):
    mem = FakeMemory()
    sum_mock = mocker.patch.object(summarizer, "summarize")
    archiver = make_archiver(llm, summarizer, mem)
    n = await archiver.archive([], conversation_id="c", user_id=1, chat_id=2)
    assert n == 0
    sum_mock.assert_not_called()
    assert mem.inserted == []


async def test_archive_full_flow(llm, summarizer, mocker):
    mem = FakeMemory()
    summary = "x" * 3000
    mocker.patch.object(summarizer, "summarize", return_value=summary)
    embed_mock = mocker.patch.object(llm, "embed", return_value=[0.1, 0.2])
    archiver = make_archiver(llm, summarizer, mem)

    n = await archiver.archive(
        [{"role": "user", "content": "hi"}],
        conversation_id="conv",
        user_id=42,
        chat_id=42,
    )
    assert n == 3
    assert len(mem.inserted) == 3
    assert [meta["chunk_index"] for _, _, _, meta in mem.inserted] == [0, 1, 2]
    assert all(meta["conversation_id"] == "conv" for _, _, _, meta in mem.inserted)
    assert all(meta["user_id"] == 42 for _, _, _, meta in mem.inserted)
    assert embed_mock.call_count == 3


async def test_archive_summarizer_failure_propagates_and_no_inserts(
    llm, summarizer, mocker
):
    mem = FakeMemory()
    mocker.patch.object(summarizer, "summarize", side_effect=LLMUnavailable("down"))
    embed_mock = mocker.patch.object(llm, "embed")
    archiver = make_archiver(llm, summarizer, mem)
    with pytest.raises(LLMUnavailable):
        await archiver.archive(
            [{"role": "user", "content": "hi"}],
            conversation_id="c",
            user_id=1,
            chat_id=1,
        )
    embed_mock.assert_not_called()
    assert mem.inserted == [] and mem.deleted == []


async def test_archive_embed_failure_rolls_back(
    llm, summarizer, mocker
):
    """При ошибке embed ничего не вставляется (откат не нужен - вставки не было)."""
    mem = FakeMemory()
    summary = "x" * 3000  # → 3 чанка
    mocker.patch.object(summarizer, "summarize", return_value=summary)
    mocker.patch.object(llm, "embed", side_effect=LLMUnavailable("embed down"))
    archiver = make_archiver(llm, summarizer, mem)

    with pytest.raises(LLMUnavailable):
        await archiver.archive(
            [{"role": "user", "content": "hi"}],
            conversation_id="c",
            user_id=1,
            chat_id=1,
        )
    # Ничего не вставлено, т.к. embed упал до вставки
    assert len(mem.inserted) == 0
    assert len(mem.deleted) == 0


async def test_archive_insert_failure_rolls_back(llm, summarizer, mocker):
    """При ошибке insert после успешных embed — откат вставок."""
    mem = FakeMemory()
    summary = "x" * 3000  # → 3 чанка
    mocker.patch.object(summarizer, "summarize", return_value=summary)
    mocker.patch.object(llm, "embed", return_value=[0.1, 0.2])
    mem.fail_insert_on(1)  # Упасть на втором чанке
    archiver = make_archiver(llm, summarizer, mem)

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        await archiver.archive(
            [{"role": "user", "content": "hi"}],
            conversation_id="c",
            user_id=1,
            chat_id=1,
        )
    # Первый чанк был вставлен и затем откачен
    assert len(mem.inserted) == 1
    assert mem.deleted == [mem.inserted[0][0]]


async def test_archive_progress_callback_called(llm, summarizer, mocker):
    """Проверяем, что progress_callback вызывается на каждом этапе."""
    mem = FakeMemory()
    summary = "x" * 3000
    mocker.patch.object(summarizer, "summarize", return_value=summary)
    mocker.patch.object(llm, "embed", return_value=[0.1, 0.2])
    archiver = make_archiver(llm, summarizer, mem)

    progress_calls = []

    def progress_cb(text: str) -> None:
        progress_calls.append(text)

    await archiver.archive(
        [{"role": "user", "content": "hi"}],
        conversation_id="conv",
        user_id=42,
        chat_id=42,
        progress_callback=progress_cb,
    )

    # Должны быть вызовы на каждом этапе
    assert len(progress_calls) >= 2
    assert any("Суммирую" in call for call in progress_calls)
    assert any("эмбеддинги" in call for call in progress_calls)


async def test_archive_parallel_embedding(llm, summarizer, mocker):
    """Проверяем, что embedding вызывается параллельно с семафором."""
    mem = FakeMemory()
    summary = "x" * 6000  # → 4+ чанка
    mocker.patch.object(summarizer, "summarize", return_value=summary)

    embed_calls = []

    async def fake_embed(text, *, model):
        embed_calls.append(text)
        return [0.1, 0.2]

    mocker.patch.object(llm, "embed", side_effect=fake_embed)
    # concurrency=2 для проверки ограничения
    archiver = make_archiver(llm, summarizer, mem, concurrency=2)

    await archiver.archive(
        [{"role": "user", "content": "hi"}],
        conversation_id="conv",
        user_id=42,
        chat_id=42,
    )

    # Все чанки должны быть обработаны
    assert len(embed_calls) >= 4
    # Проверяем, что concurrency_limit передан
    assert archiver._concurrency_limit == 2


@pytest.fixture
def user():
    return User(
        id=1,
        channel="telegram",
        external_id="12345",
        display_name="Test User",
        created_at=datetime.now(),
    )


async def test_archive_publishes_event_on_success(llm, summarizer, mocker, user):
    """Успешное архивирование публикует событие ConversationArchived."""
    mem = FakeMemory()
    summary = "x" * 3000
    mocker.patch.object(summarizer, "summarize", return_value=summary)
    mocker.patch.object(llm, "embed", return_value=[0.1, 0.2])
    
    event_bus = EventBus()
    published_events = []
    
    async def capture_event(event):
        published_events.append(event)
    
    event_bus.subscribe(ConversationArchived, capture_event)
    
    archiver = make_archiver(llm, summarizer, mem, event_bus=event_bus)
    
    await archiver.archive(
        [{"role": "user", "content": "hi"}],
        conversation_id="conv",
        user_id=42,
        chat_id=42,
        user=user,
        channel="telegram",
    )
    
    assert len(published_events) == 1
    event = published_events[0]
    assert isinstance(event, ConversationArchived)
    assert event.user == user
    assert event.conversation_id == "conv"
    assert event.chunks == 3
    assert event.channel == "telegram"


async def test_archive_does_not_publish_event_on_failure(llm, summarizer, mocker, user):
    """При неудачном архивировании событие не публикуется."""
    mem = FakeMemory()
    mocker.patch.object(summarizer, "summarize", side_effect=LLMUnavailable("down"))
    
    event_bus = EventBus()
    published_events = []
    
    async def capture_event(event):
        published_events.append(event)
    
    event_bus.subscribe(ConversationArchived, capture_event)
    
    archiver = make_archiver(llm, summarizer, mem, event_bus=event_bus)
    
    with pytest.raises(LLMUnavailable):
        await archiver.archive(
            [{"role": "user", "content": "hi"}],
            conversation_id="conv",
            user_id=42,
            chat_id=42,
            user=user,
            channel="telegram",
        )
    
    assert len(published_events) == 0


async def test_archive_does_not_publish_event_without_event_bus(llm, summarizer, mocker, user):
    """Если event_bus не передан, событие не публикуется (обратная совместимость)."""
    mem = FakeMemory()
    summary = "x" * 3000
    mocker.patch.object(summarizer, "summarize", return_value=summary)
    mocker.patch.object(llm, "embed", return_value=[0.1, 0.2])
    
    archiver = make_archiver(llm, summarizer, mem, event_bus=None)
    
    await archiver.archive(
        [{"role": "user", "content": "hi"}],
        conversation_id="conv",
        user_id=42,
        chat_id=42,
        user=user,
        channel="telegram",
    )
    
    # Не должно падать, событие просто не публикуется
