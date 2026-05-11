"""Тесты `app.logging_config.setup_logging`."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.config import Settings
from app.logging_config import JsonFormatter, SERVICE_NAME, setup_logging
from app.utils.tracing import bind_trace_id, bind_user_id, reset_trace_id, reset_user_id

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT = REPO_ROOT / "_prompts" / "agent_system.md"


@pytest.fixture
def base_settings(monkeypatch, tmp_path) -> Settings:
    for key in ("TELEGRAM_BOT_TOKEN", "AGENT_SYSTEM_PROMPT_PATH", "LOG_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setenv("AGENT_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "subdir" / "agent.log"))
    return Settings(_env_file=None)


def _teardown_root() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)


def test_setup_logging_creates_file_and_writes_json(base_settings):
    log_path = base_settings.log_file
    assert not log_path.parent.exists()

    try:
        setup_logging(base_settings)
        logging.getLogger("test").info("hello")
        for h in logging.getLogger().handlers:
            h.flush()

        assert log_path.parent.is_dir()
        assert log_path.exists()
        line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["message"] == "hello"
        assert payload["level"] == "INFO"
        assert payload["service"] == SERVICE_NAME
        assert payload["name"] == "test"
        assert "timestamp" in payload
        assert payload["trace_id"] is None
        assert payload["user_id"] is None
    finally:
        _teardown_root()


def test_json_log_contains_trace_id_and_user_id_from_contextvars(base_settings):
    log_path = base_settings.log_file
    try:
        setup_logging(base_settings)
        t_tok = bind_trace_id("abc123def456")
        u_tok = bind_user_id(4242)
        try:
            logging.getLogger("test").info("bound")
            for h in logging.getLogger().handlers:
                h.flush()
        finally:
            reset_trace_id(t_tok)
            reset_user_id(u_tok)

        line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["trace_id"] == "abc123def456"
        assert payload["user_id"] == 4242
    finally:
        _teardown_root()


def test_json_formatter_includes_extra_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.svc",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="external.call",
        args=(),
        exc_info=None,
    )
    record.duration_ms = 42
    record.model = "qwen3.5:4b"

    out = formatter.format(record)
    payload = json.loads(out)
    assert payload["message"] == "external.call"
    assert payload["extra"]["duration_ms"] == 42
    assert payload["extra"]["model"] == "qwen3.5:4b"


def test_json_formatter_serialises_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="x", level=logging.ERROR, pathname=__file__,
            lineno=1, msg="failed", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "ValueError: boom" in payload["exc_info"]
