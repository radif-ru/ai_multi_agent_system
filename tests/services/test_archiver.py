"""Тесты `app.services.archiver.Archiver`."""

from __future__ import annotations

import pytest

from app.services.archiver import Archiver, chunk_text
from app.services.llm import LLMUnavailable, OllamaClient
from app.services.summarizer import Summarizer


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


def make_archiver(llm, summarizer, memory, *, size=1500, overlap=150) -> Archiver:
    return Archiver(
        llm=llm,
        summarizer=summarizer,
        semantic_memory=memory,
        summarizer_model="qwen3.5:4b",
        embedding_model="nomic-embed-text",
        chunk_size=size,
        chunk_overlap=overlap,
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


async def test_archive_embed_failure_on_second_chunk_rolls_back(
    llm, summarizer, mocker
):
    mem = FakeMemory()
    summary = "x" * 3000  # → 3 чанка
    mocker.patch.object(summarizer, "summarize", return_value=summary)

    calls = {"n": 0}

    async def fake_embed(text, *, model):
        calls["n"] += 1
        if calls["n"] == 2:
            raise LLMUnavailable("embed down")
        return [0.0, 0.1]

    mocker.patch.object(llm, "embed", side_effect=fake_embed)
    archiver = make_archiver(llm, summarizer, mem)

    with pytest.raises(LLMUnavailable):
        await archiver.archive(
            [{"role": "user", "content": "hi"}],
            conversation_id="c",
            user_id=1,
            chat_id=1,
        )
    # первый чанк был вставлен и затем откачен
    assert len(mem.inserted) == 1
    assert mem.deleted == [mem.inserted[0][0]]
