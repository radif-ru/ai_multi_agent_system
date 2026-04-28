"""Smoke-тест точки входа `app.main`.

См. `_docs/testing.md` §3.11. Сетевая часть (`bot.set_my_commands` +
`dispatcher.start_polling`) патчится одной точкой `_start_polling`,
чтобы тест работал офлайн и быстро.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app import main as main_module
from app.main import main

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT = REPO_ROOT / "_prompts" / "agent_system.md"

ENV_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "OLLAMA_BASE_URL",
    "OLLAMA_DEFAULT_MODEL",
    "OLLAMA_AVAILABLE_MODELS",
    "OLLAMA_TIMEOUT",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "AGENT_MAX_STEPS",
    "AGENT_MAX_OUTPUT_CHARS",
    "HISTORY_MAX_MESSAGES",
    "HISTORY_SUMMARY_THRESHOLD",
    "SUMMARIZATION_PROMPT",
    "MEMORY_DB_PATH",
    "MEMORY_CHUNK_SIZE",
    "MEMORY_CHUNK_OVERLAP",
    "MEMORY_SEARCH_TOP_K",
    "AGENT_SYSTEM_PROMPT_PATH",
    "LOG_LEVEL",
    "LOG_FILE",
    "LOG_LLM_CONTEXT",
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Минимально-валидный токен для aiogram (regex `^\d+:[\w-]+$`).
    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "123456789:AAFakeTokenForSmokeTesting_0123456789",
    )
    monkeypatch.setenv("AGENT_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT))
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "agent.log"))
    return monkeypatch


def test_main_is_async_callable() -> None:
    """`python -c "from app.main import main; print(main)"` не падает."""
    assert callable(main)
    assert asyncio.iscoroutinefunction(main)


@pytest.mark.asyncio
async def test_main_logs_bot_started_and_closes(
    env: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    polling = AsyncMock()
    monkeypatch.setattr(main_module, "_start_polling", polling)

    shutdown_calls: list[tuple] = []
    real_shutdown = main_module._shutdown

    async def spy_shutdown(bot, components):
        shutdown_calls.append((bot, components))
        await real_shutdown(bot, components)

    monkeypatch.setattr(main_module, "_shutdown", spy_shutdown)

    await main()

    polling.assert_awaited_once()
    assert len(shutdown_calls) == 1
    # `setup_logging` пересобирает root-логгер, поэтому caplog не видит
    # сообщения; читаем файл логов (путь задан через LOG_FILE в фикстуре).
    import os

    log_path = Path(os.environ["LOG_FILE"])
    assert log_path.exists()
    assert "Bot started" in log_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_main_shuts_down_when_polling_raises(
    env: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Если polling упал — shutdown всё равно вызывается (finally)."""
    polling = AsyncMock(side_effect=RuntimeError("polling crashed"))
    monkeypatch.setattr(main_module, "_start_polling", polling)

    shutdown_called = AsyncMock()
    monkeypatch.setattr(main_module, "_shutdown", shutdown_called)

    with pytest.raises(RuntimeError, match="polling crashed"):
        await main()

    shutdown_called.assert_awaited_once()
