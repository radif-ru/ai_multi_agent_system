"""Тесты handler'ов команд Telegram-адаптера.

См. `_docs/commands.md` (контракт), `_docs/testing.md` §3.11 (кейсы).
Команда `/new` тестируется в задаче 6.4 — отдельным файлом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.handlers.commands import build_command_handlers
from app.services.conversation import ConversationStore
from app.services.model_registry import UserSettingsRegistry


# ---------- Фейки и фабрики ---------------------------------------------------


@dataclass
class _FakeSettings:
    ollama_default_model: str = "qwen3.5:4b"
    ollama_available_models: list[str] = field(
        default_factory=lambda: ["qwen3.5:4b", "llama3:8b"]
    )


class _FakePrompts:
    def __init__(self, template: str = "system prompt template") -> None:
        self.agent_system_template = template


class _FakeRegistry:
    """Имитирует tools-/skills-registry в части `list_descriptions`."""

    def __init__(self, descriptions: list[dict[str, Any]]) -> None:
        self._descriptions = descriptions

    def list_descriptions(self) -> list[dict[str, Any]]:
        return list(self._descriptions)


def _make_handlers(
    *,
    settings: _FakeSettings | None = None,
    user_settings: UserSettingsRegistry | None = None,
    prompts: _FakePrompts | None = None,
    tools: _FakeRegistry | None = None,
    skills: _FakeRegistry | None = None,
    conversations: ConversationStore | None = None,
) -> dict[str, Any]:
    return build_command_handlers(
        settings=settings or _FakeSettings(),
        user_settings=user_settings or UserSettingsRegistry(default_model="qwen3.5:4b"),
        prompts=prompts or _FakePrompts(),
        tools=tools
        or _FakeRegistry(
            [{"name": "calculator", "description": "арифметика"}]
        ),
        skills=skills or _FakeRegistry([{"name": "demo", "description": "пример"}]),
        conversations=conversations or ConversationStore(max_messages=10),
    )


def _make_message(
    user_id: int = 42, text: str = "/start"
) -> tuple[MagicMock, AsyncMock]:
    """Минимальный mock сообщения с .from_user.id и async .answer."""
    msg = MagicMock(spec=["from_user", "answer", "text"])
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.answer = AsyncMock()
    return msg, msg.answer


def _command(args: str | None) -> Any:
    cmd = MagicMock()
    cmd.args = args
    return cmd


# ---------- /start -----------------------------------------------------------


@pytest.mark.asyncio
async def test_start_sends_greeting() -> None:
    handlers = _make_handlers()
    msg, answer = _make_message()
    await handlers["start"](msg)
    answer.assert_awaited_once()
    text = answer.await_args.args[0]
    assert "AI-агент" in text
    assert "/help" in text and "/model" in text and "/reset" in text


# ---------- /help ------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_includes_model_prompt_tools_skills() -> None:
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    user_settings.set_model(42, "llama3:8b")
    handlers = _make_handlers(
        user_settings=user_settings,
        prompts=_FakePrompts("дефолтный системный промпт"),
        tools=_FakeRegistry(
            [{"name": "calculator", "description": "арифметика"}]
        ),
        skills=_FakeRegistry(
            [{"name": "demo-skill", "description": "пример скилла"}]
        ),
    )
    msg, answer = _make_message()
    await handlers["help"](msg)

    text = answer.await_args.args[0]
    # Команды
    assert "/model" in text and "/prompt" in text and "/reset" in text
    # Текущая модель — берётся из user_settings
    assert "llama3:8b" in text
    # Системный промпт (default)
    assert "дефолтный системный промпт" in text
    assert "по умолчанию" in text
    # Tools / skills
    assert "calculator" in text and "арифметика" in text
    assert "demo-skill" in text and "пример скилла" in text


@pytest.mark.asyncio
async def test_help_shows_user_prompt_override() -> None:
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    user_settings.set_prompt(42, "мой кастомный промпт")
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["help"](msg)
    text = answer.await_args.args[0]
    assert "мой кастомный промпт" in text
    assert "пользовательский" in text


# ---------- /models ----------------------------------------------------------


@pytest.mark.asyncio
async def test_models_lists_with_active_marker() -> None:
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    user_settings.set_model(42, "llama3:8b")
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["models"](msg)

    text = answer.await_args.args[0]
    assert "qwen3.5:4b" in text and "llama3:8b" in text
    # Активной должна быть llama3:8b — у её строки маркер.
    active_line = next(line for line in text.splitlines() if "llama3:8b" in line)
    assert "активная" in active_line
    other_line = next(
        line for line in text.splitlines() if "qwen3.5:4b" in line
    )
    assert "активная" not in other_line


# ---------- /model -----------------------------------------------------------


@pytest.mark.asyncio
async def test_model_known_calls_set_model() -> None:
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["model"](msg, _command("llama3:8b"))
    assert user_settings.get_model(42) == "llama3:8b"
    answer.assert_awaited_once()
    assert "llama3:8b" in answer.await_args.args[0]


@pytest.mark.asyncio
async def test_model_unknown_does_not_call_set_model() -> None:
    user_settings = MagicMock(wraps=UserSettingsRegistry(default_model="qwen3.5:4b"))
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["model"](msg, _command("ghost-model"))
    user_settings.set_model.assert_not_called()
    text = answer.await_args.args[0]
    assert "не найдена" in text


@pytest.mark.asyncio
async def test_model_no_arg_shows_usage() -> None:
    user_settings = MagicMock(wraps=UserSettingsRegistry(default_model="qwen3.5:4b"))
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["model"](msg, _command(None))
    user_settings.set_model.assert_not_called()
    assert "/model" in answer.await_args.args[0]


# ---------- /prompt ----------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_with_text_calls_set_prompt() -> None:
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["prompt"](msg, _command("ты — лаконичный ассистент"))
    assert user_settings.get_prompt(42) == "ты — лаконичный ассистент"
    assert "обновлён" in answer.await_args.args[0]


@pytest.mark.asyncio
async def test_prompt_no_arg_calls_reset_prompt() -> None:
    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    user_settings.set_prompt(42, "старый")
    handlers = _make_handlers(user_settings=user_settings)
    msg, answer = _make_message()
    await handlers["prompt"](msg, _command(None))
    assert user_settings.get_prompt(42) is None
    assert "сброш" in answer.await_args.args[0]


# ---------- /reset -----------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_conversation_and_settings() -> None:
    conversations = ConversationStore(max_messages=10)
    conversations.add_user_message(42, "привет")
    cid_before = conversations.current_conversation_id(42)

    user_settings = UserSettingsRegistry(default_model="qwen3.5:4b")
    user_settings.set_model(42, "llama3:8b")
    user_settings.set_prompt(42, "custom")

    handlers = _make_handlers(
        user_settings=user_settings, conversations=conversations
    )
    msg, answer = _make_message()
    await handlers["reset"](msg)

    assert conversations.get_history(42) == []
    assert user_settings.get_model(42) == "qwen3.5:4b"
    assert user_settings.get_prompt(42) is None
    cid_after = conversations.current_conversation_id(42)
    assert cid_after != cid_before
    assert "очищен" in answer.await_args.args[0]
