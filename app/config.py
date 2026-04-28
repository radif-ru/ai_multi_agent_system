"""Конфигурация приложения.

Поля и валидаторы — по `_docs/stack.md` §9 и `_docs/architecture.md` §3.2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str

    # --- Ollama (LLM) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "qwen3.5:4b"
    ollama_available_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["qwen3.5:4b"]
    )
    ollama_timeout: float = 120.0

    # --- Ollama (Embedding) ---
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # --- Agent loop ---
    agent_max_steps: int = 10
    agent_max_output_chars: int = 8000

    # --- Memory (in-memory) ---
    history_max_messages: int = 20
    history_summary_threshold: int = 10
    session_log_max_messages: int = 1000
    summarization_prompt: str = (
        "Кратко и точно резюмируй ключевые факты и решения из этого диалога "
        "в 2–4 предложениях. Ответ — только текст резюме, без вступлений."
    )

    # --- Memory (long-term) ---
    memory_db_path: Path = Path("data/memory.db")
    memory_chunk_size: int = 1500
    memory_chunk_overlap: int = 150
    memory_search_top_k: int = 5
    session_bootstrap_enabled: bool = True
    session_bootstrap_top_k: int = 3

    # --- Prompts ---
    agent_system_prompt_path: Path = Path("_prompts/agent_system.md")

    # --- Logging ---
    log_level: str = "INFO"
    log_file: Path = Path("logs/agent.log")
    log_llm_context: bool = True

    @field_validator("ollama_available_models", mode="before")
    @classmethod
    def _parse_models_csv(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("embedding_dimensions")
    @classmethod
    def _check_embedding_dim(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be > 0")
        return v

    @field_validator("session_bootstrap_top_k")
    @classmethod
    def _check_bootstrap_top_k(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("SESSION_BOOTSTRAP_TOP_K must be > 0")
        return v

    @field_validator("history_max_messages")
    @classmethod
    def _check_history_max(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("HISTORY_MAX_MESSAGES must be > 0")
        return v

    @field_validator("history_summary_threshold")
    @classmethod
    def _check_history_threshold(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("HISTORY_SUMMARY_THRESHOLD must be > 0")
        return v

    @field_validator("session_log_max_messages")
    @classmethod
    def _check_session_log_max(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("SESSION_LOG_MAX_MESSAGES must be > 0")
        return v

    @model_validator(mode="after")
    def _cross_validate(self) -> "Settings":
        if self.ollama_default_model not in self.ollama_available_models:
            raise ValueError(
                f"OLLAMA_DEFAULT_MODEL '{self.ollama_default_model}' "
                f"not in OLLAMA_AVAILABLE_MODELS {self.ollama_available_models}"
            )
        if self.history_summary_threshold > self.history_max_messages:
            raise ValueError(
                "HISTORY_SUMMARY_THRESHOLD must be <= HISTORY_MAX_MESSAGES"
            )
        if not self.agent_system_prompt_path.exists():
            raise ValueError(
                f"AGENT_SYSTEM_PROMPT_PATH does not exist: {self.agent_system_prompt_path}"
            )
        return self
