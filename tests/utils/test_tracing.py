"""Тесты `app.utils.tracing`."""

from __future__ import annotations

import asyncio

from app.utils.tracing import (
    bind_trace_id,
    bind_user_id,
    get_trace_id,
    get_user_id,
    new_trace_id,
    reset_trace_id,
    reset_user_id,
)


def test_new_trace_id_is_unique_and_short():
    a = new_trace_id()
    b = new_trace_id()
    assert a != b
    assert len(a) == 12
    assert all(c in "0123456789abcdef" for c in a)


def test_bind_and_get_trace_id_roundtrip():
    assert get_trace_id() is None
    tok = bind_trace_id("deadbeef")
    try:
        assert get_trace_id() == "deadbeef"
    finally:
        reset_trace_id(tok)
    assert get_trace_id() is None


def test_bind_user_id_roundtrip():
    assert get_user_id() is None
    tok = bind_user_id(123)
    try:
        assert get_user_id() == 123
    finally:
        reset_user_id(tok)
    assert get_user_id() is None


def test_trace_id_isolated_per_asyncio_task():
    async def run() -> tuple[str | None, str | None]:
        async def worker(value: str) -> str | None:
            tok = bind_trace_id(value)
            try:
                await asyncio.sleep(0)
                return get_trace_id()
            finally:
                reset_trace_id(tok)

        results = await asyncio.gather(worker("aaa"), worker("bbb"))
        return tuple(results)  # type: ignore[return-value]

    a, b = asyncio.run(run())
    assert {a, b} == {"aaa", "bbb"}
    assert get_trace_id() is None
