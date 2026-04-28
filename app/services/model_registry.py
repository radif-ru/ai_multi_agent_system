"""Per-user настройки агента: выбранная модель и системный промпт.

См. `_docs/architecture.md` § Telegram-адаптер и `_docs/commands.md`
§ `/model`, `/prompt`, `/reset`.

Хранилище — in-memory; данные не переживают рестарт процесса (это сознательное
ограничение MVP, см. `_docs/mvp.md` §3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class _UserState:
    model: str | None = None
    prompt: str | None = None


class UserSettingsRegistry:
    """Реестр per-user override'ов модели и системного промпта.

    Валидация имени модели в этот класс **не входит** — это ответственность
    handler'а команды `/model` (он знает список `OLLAMA_AVAILABLE_MODELS`).
    """

    def __init__(self, default_model: str) -> None:
        self._default_model = default_model
        self._states: dict[int, _UserState] = {}

    def get_model(self, user_id: int) -> str:
        state = self._states.get(user_id)
        if state is None or state.model is None:
            return self._default_model
        return state.model

    def set_model(self, user_id: int, model_name: str) -> None:
        self._states.setdefault(user_id, _UserState()).model = model_name

    def get_prompt(self, user_id: int) -> str | None:
        """Возвращает per-user override системного промпта или None (= default)."""
        state = self._states.get(user_id)
        return None if state is None else state.prompt

    def set_prompt(self, user_id: int, text: str) -> None:
        self._states.setdefault(user_id, _UserState()).prompt = text

    def reset_prompt(self, user_id: int) -> None:
        state = self._states.get(user_id)
        if state is not None:
            state.prompt = None

    def reset(self, user_id: int) -> None:
        """Полный сброс per-user настроек (модель и промпт → default)."""
        self._states.pop(user_id, None)
