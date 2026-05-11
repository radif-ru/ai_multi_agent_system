"""Unit-тесты для `app.observability.setup_sentry` и хука `_before_send`.

Проверяют:

1. `setup_sentry` не инициализирует `sentry_sdk`, если DSN пустой (off-by-default).
2. `setup_sentry` вызывает `sentry_sdk.init` с правильными аргументами при заданном DSN.
3. Хук `_before_send` подмешивает `trace_id` и `user_id` из contextvars.
4. Хук `_before_send` не валится, если контекст пуст (trace_id/user_id = None).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.observability import _before_send, setup_sentry
from app.utils.tracing import (
    bind_trace_id,
    bind_user_id,
    reset_trace_id,
    reset_user_id,
)


def _make_settings(**overrides):
    base = dict(
        sentry_dsn=None,
        sentry_environment="dev",
        sentry_traces_sample_rate=0.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_setup_sentry_skipped_when_dsn_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой DSN => sentry_sdk.init не вызывается, сеть не дёргается."""
    import sentry_sdk

    init_mock = MagicMock()
    monkeypatch.setattr(sentry_sdk, "init", init_mock)

    assert setup_sentry(_make_settings(sentry_dsn=None)) is False
    assert setup_sentry(_make_settings(sentry_dsn="")) is False
    init_mock.assert_not_called()


def test_setup_sentry_initializes_when_dsn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Заданный DSN => sentry_sdk.init вызван с before_send и environment."""
    import sentry_sdk
    from app import observability as obs

    init_mock = MagicMock()
    monkeypatch.setattr(sentry_sdk, "init", init_mock)

    settings = _make_settings(
        sentry_dsn="https://pub@glitchtip.example.com/1",
        sentry_environment="prod",
        sentry_traces_sample_rate=0.25,
    )
    assert setup_sentry(settings) is True

    init_mock.assert_called_once()
    kwargs = init_mock.call_args.kwargs
    assert kwargs["dsn"] == "https://pub@glitchtip.example.com/1"
    assert kwargs["environment"] == "prod"
    assert kwargs["traces_sample_rate"] == 0.25
    assert kwargs["send_default_pii"] is False
    assert kwargs["before_send"] is obs._before_send


def test_before_send_enriches_event_with_trace_id_and_user_id() -> None:
    """Хук подмешивает trace_id в tags/extra, user_id в user.id."""
    trace_token = bind_trace_id("abc123def456")
    user_token = bind_user_id(42)
    try:
        event = _before_send({}, {})
    finally:
        reset_user_id(user_token)
        reset_trace_id(trace_token)

    assert event is not None
    assert event["tags"]["trace_id"] == "abc123def456"
    assert event["extra"]["trace_id"] == "abc123def456"
    assert event["user"]["id"] == "42"


def test_before_send_noop_when_context_empty() -> None:
    """Без установленного контекста хук ничего не добавляет и не падает."""
    event = _before_send({}, {})
    assert event == {}
