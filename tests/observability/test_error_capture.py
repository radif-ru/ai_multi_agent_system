"""Smoke-тест: четыре класса искусственных ошибок доезжают до Sentry.

См. _board/sprints/06-reliability-and-observability.md §8, задача 5.3.

Подменяем реальный transport у `sentry_sdk` на in-memory буфер, прогоняем
четыре сценария ошибок через `setup_sentry(...)` и `sentry_sdk.capture_exception(...)`,
проверяем что для каждого:

- событие попало в transport,
- `event.exception` содержит стек (`stacktrace`),
- `event.tags.trace_id` == установленный `trace_id` (через `bind_trace_id`).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.observability import setup_sentry
from app.utils.tracing import bind_trace_id, reset_trace_id


class _InMemoryTransport(Transport):
    """Transport, который вместо отправки складывает envelopes в список."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options or {})
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope) -> None:  # noqa: D401
        for item in envelope.items:
            if item.headers.get("type") == "event":
                self.events.append(item.payload.json)


def _make_settings(dsn: str = "https://pub@glitchtip.test/1") -> SimpleNamespace:
    return SimpleNamespace(
        sentry_dsn=dsn,
        sentry_environment="test",
        sentry_traces_sample_rate=0.0,
    )


@pytest.fixture
def sentry_transport(monkeypatch: pytest.MonkeyPatch):
    """Инициализировать sentry_sdk с in-memory transport через setup_sentry."""
    transport = _InMemoryTransport()

    original_init = sentry_sdk.init

    def patched_init(*args, **kwargs):
        kwargs["transport"] = transport
        return original_init(*args, **kwargs)

    monkeypatch.setattr(sentry_sdk, "init", patched_init)

    assert setup_sentry(_make_settings()) is True
    try:
        yield transport
    finally:
        client = sentry_sdk.get_client()
        client.close(timeout=2.0)


def _last_event(transport: _InMemoryTransport) -> dict[str, Any]:
    sentry_sdk.flush(timeout=2.0)
    assert transport.events, "ожидалось хотя бы одно событие в transport"
    return transport.events[-1]


def _assert_has_stacktrace(event: dict[str, Any]) -> None:
    assert "exception" in event, f"event без exception: {event}"
    values = event["exception"].get("values", [])
    assert values, f"пустой exception.values: {event}"
    assert "stacktrace" in values[-1], f"нет stacktrace: {values[-1]}"


def _assert_trace_id(event: dict[str, Any], trace_id: str) -> None:
    tags = event.get("tags") or {}
    if isinstance(tags, list):  # sentry может хранить tags как list[tuple]
        tags = dict(tags)
    assert tags.get("trace_id") == trace_id, f"tags={tags}"


def test_capture_manual_value_error(sentry_transport: _InMemoryTransport) -> None:
    """Сценарий 1: ручной `raise ValueError`."""
    token = bind_trace_id("trace-manual-01")
    try:
        try:
            raise ValueError("boom manual")
        except ValueError:
            sentry_sdk.capture_exception()
        event = _last_event(sentry_transport)
        _assert_has_stacktrace(event)
        _assert_trace_id(event, "trace-manual-01")
        assert event["exception"]["values"][-1]["type"] == "ValueError"
    finally:
        reset_trace_id(token)


def test_capture_error_from_create_task(sentry_transport: _InMemoryTransport) -> None:
    """Сценарий 2: исключение внутри `asyncio.create_task` доезжает до Sentry."""

    async def runner() -> None:
        async def worker() -> None:
            raise RuntimeError("boom async")

        task = asyncio.create_task(worker())
        try:
            await task
        except RuntimeError:
            sentry_sdk.capture_exception()

    token = bind_trace_id("trace-async-02")
    try:
        asyncio.run(runner())
        event = _last_event(sentry_transport)
        _assert_has_stacktrace(event)
        _assert_trace_id(event, "trace-async-02")
        assert event["exception"]["values"][-1]["type"] == "RuntimeError"
    finally:
        reset_trace_id(token)


def test_capture_httpx_timeout(sentry_transport: _InMemoryTransport) -> None:
    """Сценарий 3: ошибка внешнего вызова (httpx.TimeoutException)."""
    token = bind_trace_id("trace-http-03")
    try:
        try:
            raise httpx.TimeoutException("upstream timeout")
        except httpx.TimeoutException:
            sentry_sdk.capture_exception()
        event = _last_event(sentry_transport)
        _assert_has_stacktrace(event)
        _assert_trace_id(event, "trace-http-03")
        assert event["exception"]["values"][-1]["type"] == "TimeoutException"
    finally:
        reset_trace_id(token)


def test_capture_json_decode_error(sentry_transport: _InMemoryTransport) -> None:
    """Сценарий 4: ошибка данных (JSONDecodeError на невалидном JSON)."""
    token = bind_trace_id("trace-data-04")
    try:
        try:
            json.loads("{not: valid json")
        except json.JSONDecodeError:
            sentry_sdk.capture_exception()
        event = _last_event(sentry_transport)
        _assert_has_stacktrace(event)
        _assert_trace_id(event, "trace-data-04")
        assert event["exception"]["values"][-1]["type"] == "JSONDecodeError"
    finally:
        reset_trace_id(token)
