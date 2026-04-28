"""Тесты `app/services/session_bootstrap.py`. См. `_docs/memory.md` §3.6."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.session_bootstrap import (
    BOOTSTRAP_HEADER,
    build_bootstrap_message,
)


@dataclass
class _Settings:
    embedding_model: str = "nomic-embed-text"
    session_bootstrap_enabled: bool = True
    session_bootstrap_top_k: int = 3


class _FakeLLM:
    def __init__(self, *, embedding: list[float] | None = None, exc: Exception | None = None) -> None:
        self._embedding = embedding or [0.1, 0.2, 0.3]
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def embed(self, text: str, *, model: str) -> list[float]:
        self.calls.append({"text": text, "model": model})
        if self._exc is not None:
            raise self._exc
        return self._embedding


class _FakeMemory:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None, exc: Exception | None = None) -> None:
        self._rows = rows or []
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def search(self, embedding: list[float], *, top_k: int, scope_user_id: int) -> list[dict[str, Any]]:
        self.calls.append({"embedding": embedding, "top_k": top_k, "scope_user_id": scope_user_id})
        if self._exc is not None:
            raise self._exc
        return self._rows


async def test_returns_system_message_with_chunks() -> None:
    llm = _FakeLLM()
    memory = _FakeMemory(rows=[{"text": "факт 1"}, {"text": "факт 2"}])
    msg = await build_bootstrap_message(
        query="как меня зовут?",
        user_id=42,
        settings=_Settings(),
        llm=llm,
        semantic_memory=memory,
    )
    assert msg is not None
    assert msg["role"] == "system"
    assert BOOTSTRAP_HEADER in msg["content"]
    assert "- факт 1" in msg["content"]
    assert "- факт 2" in msg["content"]
    assert llm.calls[0]["model"] == "nomic-embed-text"
    assert memory.calls[0]["top_k"] == 3
    assert memory.calls[0]["scope_user_id"] == 42


async def test_returns_none_when_disabled() -> None:
    llm = _FakeLLM()
    memory = _FakeMemory(rows=[{"text": "x"}])
    msg = await build_bootstrap_message(
        query="q",
        user_id=1,
        settings=_Settings(session_bootstrap_enabled=False),
        llm=llm,
        semantic_memory=memory,
    )
    assert msg is None
    assert llm.calls == []
    assert memory.calls == []


async def test_returns_none_when_memory_missing() -> None:
    msg = await build_bootstrap_message(
        query="q", user_id=1, settings=_Settings(),
        llm=_FakeLLM(), semantic_memory=None,
    )
    assert msg is None


async def test_returns_none_when_llm_missing() -> None:
    msg = await build_bootstrap_message(
        query="q", user_id=1, settings=_Settings(),
        llm=None, semantic_memory=_FakeMemory(),
    )
    assert msg is None


async def test_returns_none_for_empty_archive() -> None:
    msg = await build_bootstrap_message(
        query="q", user_id=1, settings=_Settings(),
        llm=_FakeLLM(), semantic_memory=_FakeMemory(rows=[]),
    )
    assert msg is None


async def test_logs_warning_on_embed_failure(caplog: pytest.LogCaptureFixture) -> None:
    llm = _FakeLLM(exc=RuntimeError("boom"))
    memory = _FakeMemory()
    with caplog.at_level(logging.WARNING, logger="app.services.session_bootstrap"):
        msg = await build_bootstrap_message(
            query="q", user_id=7, settings=_Settings(),
            llm=llm, semantic_memory=memory,
        )
    assert msg is None
    assert any("session_bootstrap failed" in r.message for r in caplog.records)
    assert memory.calls == []  # search не вызывался


async def test_logs_warning_on_search_failure(caplog: pytest.LogCaptureFixture) -> None:
    memory = _FakeMemory(exc=RuntimeError("db down"))
    with caplog.at_level(logging.WARNING, logger="app.services.session_bootstrap"):
        msg = await build_bootstrap_message(
            query="q", user_id=7, settings=_Settings(),
            llm=_FakeLLM(), semantic_memory=memory,
        )
    assert msg is None
    assert any("session_bootstrap failed" in r.message for r in caplog.records)
