"""Тесты `LoggingMiddleware`.

См. `_docs/architecture.md` §3.12 и §9, `_docs/observability.md` §2.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.logging_config import ContextFilter
from app.middlewares.logging_mw import LoggingMiddleware
from app.utils.tracing import get_trace_id, get_user_id


def _make_event(*, user_id: int = 42, chat_id: int = 777) -> MagicMock:
    event = MagicMock(spec=["from_user", "chat"])
    event.from_user = MagicMock()
    event.from_user.id = user_id
    event.chat = MagicMock()
    event.chat.id = chat_id
    return event


@pytest.mark.asyncio
async def test_logs_ok_status_and_returns_handler_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    middleware = LoggingMiddleware()
    handler = AsyncMock(return_value="ok-result")
    event = _make_event()

    with caplog.at_level(logging.INFO, logger="app.middlewares.logging_mw"):
        result = await middleware(handler, event, {})

    assert result == "ok-result"
    handler.assert_awaited_once_with(event, {})
    log_lines = [r.message for r in caplog.records]
    assert any(
        "update " in line
        and "user=42" in line
        and "chat=777" in line
        and "status=ok" in line
        for line in log_lines
    )


@pytest.mark.asyncio
async def test_logs_error_status_and_propagates_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    middleware = LoggingMiddleware()
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    event = _make_event()

    with caplog.at_level(logging.INFO, logger="app.middlewares.logging_mw"):
        with pytest.raises(RuntimeError, match="boom"):
            await middleware(handler, event, {})

    log_lines = [r.message for r in caplog.records]
    assert any("status=error" in line for line in log_lines)


@pytest.mark.asyncio
async def test_binds_trace_id_and_user_id_during_handler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Внутри handler'а доступны trace_id/user_id; логи handler'а и
    middleware несут один и тот же trace_id, а после выхода он сбрасывается.
    """
    middleware = LoggingMiddleware()
    observed: dict[str, object] = {}
    inner_logger = logging.getLogger("test.inner")

    async def _handler(event, data):
        observed["trace_id"] = get_trace_id()
        observed["user_id"] = get_user_id()
        inner_logger.info("inside-handler")
        return "ok"

    event = _make_event(user_id=101)
    context_filter = ContextFilter()

    # Перехватываем trace_id/user_id у всех логов через caplog.
    caplog.handler.addFilter(context_filter)
    try:
        with caplog.at_level(logging.INFO):
            assert get_trace_id() is None
            await middleware(_handler, event, {})
            # После выхода — сброшено.
            assert get_trace_id() is None
            assert get_user_id() is None
    finally:
        caplog.handler.removeFilter(context_filter)

    assert observed["user_id"] == 101
    trace_value = observed["trace_id"]
    assert isinstance(trace_value, str) and len(trace_value) == 12

    traces = {
        getattr(rec, "trace_id", None)
        for rec in caplog.records
        if rec.name in {"test.inner", "app.middlewares.logging_mw"}
    }
    assert traces == {trace_value}, traces


@pytest.mark.asyncio
async def test_extracts_ids_from_data_for_update_without_from_user(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Регрессия: на dispatcher.update объект Update не имеет from_user/chat,
    aiogram передаёт их через data['event_from_user'] / data['event_chat'].
    """
    middleware = LoggingMiddleware()
    observed: dict[str, object] = {}

    async def _handler(event, data):
        observed["user_id"] = get_user_id()
        return "ok"

    # Update-подобный объект: ни from_user, ни chat нет.
    event = MagicMock(spec=[])
    user = MagicMock()
    user.id = 555
    chat = MagicMock()
    chat.id = 999
    data = {"event_from_user": user, "event_chat": chat}

    with caplog.at_level(logging.INFO, logger="app.middlewares.logging_mw"):
        await middleware(_handler, event, data)

    assert observed["user_id"] == 555
    assert any(
        "user=555" in r.message and "chat=999" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_trace_id_reset_on_handler_exception() -> None:
    """При исключении в handler контекст всё равно сбрасывается."""
    middleware = LoggingMiddleware()

    async def _boom(event, data):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await middleware(_boom, _make_event(), {})

    assert get_trace_id() is None
    assert get_user_id() is None
