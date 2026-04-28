"""Тесты `LoggingMiddleware`.

См. `_docs/architecture.md` §3.12 и §9.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.middlewares.logging_mw import LoggingMiddleware


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
        "update " in l
        and "user=42" in l
        and "chat=777" in l
        and "status=ok" in l
        for l in log_lines
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
    assert any("status=error" in l for l in log_lines)
