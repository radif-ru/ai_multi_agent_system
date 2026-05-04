"""Тесты глобального error handler'а Telegram-адаптера.

См. `_docs/architecture.md` §7, `_docs/testing.md` §3.11.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.handlers.errors import (
    GENERIC_ERROR_REPLY,
    build_error_handler,
)


def _make_event(*, with_message: bool = True) -> MagicMock:
    event = MagicMock()
    event.exception = RuntimeError("boom")
    if with_message:
        event.update = MagicMock()
        event.update.message = MagicMock()
        event.update.message.answer = AsyncMock()
    else:
        event.update = MagicMock()
        event.update.message = None
    return event


@pytest.mark.asyncio
async def test_handler_sends_generic_reply_and_swallows_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = build_error_handler()
    event = _make_event()

    with caplog.at_level(logging.ERROR, logger="app.adapters.telegram.handlers.errors"):
        result = await handler(event)

    assert result is True
    event.update.message.answer.assert_awaited_once_with(GENERIC_ERROR_REPLY, parse_mode=None)
    assert any("unhandled exception" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_handler_without_message_only_logs() -> None:
    handler = build_error_handler()
    event = _make_event(with_message=False)

    result = await handler(event)
    assert result is True


@pytest.mark.asyncio
async def test_handler_does_not_crash_when_answer_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = build_error_handler()
    event = _make_event()
    event.update.message.answer = AsyncMock(side_effect=RuntimeError("send failed"))

    with caplog.at_level(logging.ERROR, logger="app.adapters.telegram.handlers.errors"):
        result = await handler(event)

    assert result is True
    assert any("failed to send error reply" in r.message for r in caplog.records)
