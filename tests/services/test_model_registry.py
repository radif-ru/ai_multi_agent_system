"""Тесты `UserSettingsRegistry`."""

from __future__ import annotations

import pytest

from app.services.model_registry import UserSettingsRegistry


@pytest.fixture
def reg() -> UserSettingsRegistry:
    return UserSettingsRegistry(default_model="qwen3.5:4b")


def test_get_model_default_for_unknown_user(reg: UserSettingsRegistry) -> None:
    assert reg.get_model(42) == "qwen3.5:4b"


def test_set_and_get_model(reg: UserSettingsRegistry) -> None:
    reg.set_model(42, "llama3:8b")
    assert reg.get_model(42) == "llama3:8b"
    # Другой пользователь по-прежнему получает default.
    assert reg.get_model(7) == "qwen3.5:4b"


def test_get_prompt_none_by_default(reg: UserSettingsRegistry) -> None:
    assert reg.get_prompt(42) is None


def test_set_and_get_prompt(reg: UserSettingsRegistry) -> None:
    reg.set_prompt(42, "Ты — лаконичный ассистент.")
    assert reg.get_prompt(42) == "Ты — лаконичный ассистент."


def test_reset_prompt_returns_to_default(reg: UserSettingsRegistry) -> None:
    reg.set_prompt(42, "custom")
    reg.reset_prompt(42)
    assert reg.get_prompt(42) is None


def test_reset_prompt_for_unknown_user_is_noop(reg: UserSettingsRegistry) -> None:
    reg.reset_prompt(999)  # не должно бросать
    assert reg.get_prompt(999) is None


def test_reset_full_clears_model_and_prompt(reg: UserSettingsRegistry) -> None:
    reg.set_model(42, "llama3:8b")
    reg.set_prompt(42, "custom")
    reg.reset(42)
    assert reg.get_model(42) == "qwen3.5:4b"
    assert reg.get_prompt(42) is None


def test_reset_for_unknown_user_is_noop(reg: UserSettingsRegistry) -> None:
    reg.reset(999)
    assert reg.get_model(999) == "qwen3.5:4b"


def test_users_are_isolated(reg: UserSettingsRegistry) -> None:
    reg.set_model(1, "a:1")
    reg.set_prompt(1, "p1")
    reg.set_model(2, "b:2")
    reg.set_prompt(2, "p2")
    assert reg.get_model(1) == "a:1"
    assert reg.get_prompt(1) == "p1"
    assert reg.get_model(2) == "b:2"
    assert reg.get_prompt(2) == "p2"
    reg.reset(1)
    assert reg.get_model(2) == "b:2"
    assert reg.get_prompt(2) == "p2"
