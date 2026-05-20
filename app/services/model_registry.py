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
    search_engine: str | None = None
    reflection_mode: str | None = None


class UserSettingsRegistry:
    """Реестр per-user override'ов модели, системного промпта и поисковика.

    Валидация имени модели и поисковика в этот класс **не входит** — это ответственность
    handler'ов команд `/model` и `/search_engine` (они знают списки доступных значений).
    """

    def __init__(self, default_model: str, default_search_engine: str) -> None:
        self._default_model = default_model
        self._default_search_engine = default_search_engine
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
        """Полный сброс per-user настроек (модель, промпт, поисковик → default)."""
        self._states.pop(user_id, None)

    def get_search_engine(self, user_id: int) -> str:
        """Возвращает выбранный поисковик пользователя или дефолтный."""
        state = self._states.get(user_id)
        if state is None or state.search_engine is None:
            return self._default_search_engine
        return state.search_engine

    def set_search_engine(self, user_id: int, engine_name: str) -> None:
        """Устанавливает поисковик для пользователя."""
        self._states.setdefault(user_id, _UserState()).search_engine = engine_name

    def get_reflection_mode(self, user_id: int) -> str | None:
        """Возвращает per-user override режима рефлексии или `None` (= fallback на Settings).

        См. `_docs/multi-agent.md` и `app.config.Settings.agent_reflection_mode`.
        Валидация значения (`OFF|NORMAL|DEEP`) — ответственность handler'а команды `/mode`.
        """
        state = self._states.get(user_id)
        return None if state is None else state.reflection_mode

    def set_reflection_mode(self, user_id: int, mode: str) -> None:
        """Устанавливает per-user режим рефлексии."""
        self._states.setdefault(user_id, _UserState()).reflection_mode = mode

    def reset_reflection_mode(self, user_id: int) -> None:
        """Сбрасывает per-user режим рефлексии к дефолту из Settings."""
        state = self._states.get(user_id)
        if state is not None:
            state.reflection_mode = None
