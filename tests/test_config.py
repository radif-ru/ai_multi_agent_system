"""Тесты конфигурации (`app.config.Settings`).

Покрытие — по `_docs/testing.md` §3.1.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

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
def base_env(monkeypatch):
    """Минимальный валидный набор env-переменных, изоляция от внешнего окружения."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setenv("AGENT_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT))
    return monkeypatch


def _build(env, **overrides) -> Settings:
    for k, v in overrides.items():
        env.setenv(k, str(v))
    return Settings(_env_file=None)


def test_loads_defaults(base_env):
    s = _build(base_env)
    assert s.telegram_bot_token == "test:token"
    assert s.ollama_default_model == "qwen3.5:4b"
    assert s.ollama_available_models == ["qwen3.5:4b"]
    assert s.embedding_dimensions == 768
    assert s.history_max_messages == 20
    assert s.history_summary_threshold == 10
    assert s.agent_max_steps == 10
    assert s.agent_system_prompt_path == DEFAULT_PROMPT


def test_csv_parses_models_list(base_env):
    s = _build(
        base_env,
        OLLAMA_AVAILABLE_MODELS="qwen3.5:4b, llama3:8b ,mistral",
    )
    assert s.ollama_available_models == ["qwen3.5:4b", "llama3:8b", "mistral"]


def test_missing_token_raises(base_env):
    base_env.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_default_model_not_in_available(base_env):
    with pytest.raises(ValidationError):
        _build(
            base_env,
            OLLAMA_DEFAULT_MODEL="gpt-4",
            OLLAMA_AVAILABLE_MODELS="qwen3.5:4b",
        )


def test_summary_threshold_gt_max_raises(base_env):
    with pytest.raises(ValidationError):
        _build(base_env, HISTORY_MAX_MESSAGES=10, HISTORY_SUMMARY_THRESHOLD=20)


def test_history_max_zero_raises(base_env):
    with pytest.raises(ValidationError):
        _build(base_env, HISTORY_MAX_MESSAGES=0, HISTORY_SUMMARY_THRESHOLD=0)


def test_summary_threshold_zero_raises(base_env):
    with pytest.raises(ValidationError):
        _build(base_env, HISTORY_SUMMARY_THRESHOLD=0)


def test_embedding_dimensions_non_positive_raises(base_env):
    with pytest.raises(ValidationError):
        _build(base_env, EMBEDDING_DIMENSIONS=0)


def test_prompt_path_does_not_exist_raises(base_env, tmp_path):
    bad = tmp_path / "nope.md"
    with pytest.raises(ValidationError):
        _build(base_env, AGENT_SYSTEM_PROMPT_PATH=str(bad))
