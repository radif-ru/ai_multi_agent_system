"""Тесты `app.logging_config.setup_logging`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.config import Settings
from app.logging_config import setup_logging

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


def test_setup_logging_creates_file_and_dir(base_settings, tmp_path):
    log_path = base_settings.log_file
    assert not log_path.parent.exists()

    try:
        setup_logging(base_settings)
        logging.getLogger("test").info("hello")
        for h in logging.getLogger().handlers:
            h.flush()

        assert log_path.parent.is_dir()
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "hello" in content
    finally:
        # Закрываем хэндлеры, чтобы tmp_path можно было удалить.
        root = logging.getLogger()
        for h in list(root.handlers):
            h.close()
            root.removeHandler(h)
