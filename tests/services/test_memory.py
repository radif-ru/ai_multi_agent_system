"""Тесты `app.services.memory.SemanticMemory`.

Используется реальный `sqlite-vec` extension; если он не загружается в окружении,
все тесты модуля помечаются `pytest.skip`.
"""

from __future__ import annotations

import pytest

from app.services.memory import MemoryUnavailable, SemanticMemory


DIM = 4


@pytest.fixture
async def mem(tmp_path):
    m = SemanticMemory(db_path=tmp_path / "mem.db", dimensions=DIM)
    try:
        await m.init()
    except MemoryUnavailable as exc:
        pytest.skip(f"sqlite-vec extension not available: {exc}")
    try:
        yield m
    finally:
        await m.close()


def _meta(user_id: int = 1, idx: int = 0, conv: str = "c1") -> dict:
    return {
        "user_id": user_id,
        "chat_id": user_id,
        "conversation_id": conv,
        "chunk_index": idx,
    }


async def test_init_is_idempotent(tmp_path):
    m = SemanticMemory(db_path=tmp_path / "x.db", dimensions=DIM)
    try:
        await m.init()
    except MemoryUnavailable as exc:
        pytest.skip(str(exc))
    await m.close()
    # повторно — без ошибок
    await m.init()
    await m.close()


async def test_insert_writes_both_tables_with_same_rowid(mem):
    rowid = await mem.insert("hello", [1.0, 0.0, 0.0, 0.0], _meta())
    assert rowid > 0
    conn = mem._conn  # доступ к низкоуровневому соединению только для проверки
    chunks = conn.execute("SELECT id, text FROM memory_chunks").fetchall()
    vecs = conn.execute("SELECT rowid FROM memory_vec").fetchall()
    assert chunks == [(rowid, "hello")]
    assert vecs == [(rowid,)]


async def test_search_orders_by_distance_and_filters_by_user(mem):
    await mem.insert("near", [1.0, 0.0, 0.0, 0.0], _meta(user_id=1, idx=0))
    await mem.insert("far", [0.0, 1.0, 0.0, 0.0], _meta(user_id=1, idx=1))
    await mem.insert("other", [1.0, 0.0, 0.0, 0.0], _meta(user_id=2, idx=0, conv="c2"))

    rows = await mem.search([1.0, 0.0, 0.0, 0.0], top_k=5, scope_user_id=1)
    texts = [r["text"] for r in rows]
    assert texts[0] == "near"
    assert "other" not in texts
    # отсортировано по distance
    distances = [r["distance"] for r in rows]
    assert distances == sorted(distances)


async def test_search_empty_db_returns_empty_list(mem):
    rows = await mem.search([0.1, 0.2, 0.3, 0.4], top_k=5, scope_user_id=1)
    assert rows == []


async def test_dimension_mismatch_raises(mem):
    with pytest.raises(ValueError):
        await mem.insert("x", [1.0, 0.0], _meta())
    with pytest.raises(ValueError):
        await mem.search([1.0, 0.0], top_k=3, scope_user_id=1)


async def test_top_k_zero_returns_empty(mem):
    await mem.insert("x", [1.0, 0.0, 0.0, 0.0], _meta())
    assert await mem.search([1.0, 0.0, 0.0, 0.0], top_k=0, scope_user_id=1) == []
