"""Регрессионный e2e-тест: диалоговая память доходит до LLM.

Имитирует три последовательных текстовых сообщения от одного пользователя
и проверяет, что на третьем вызове `llm.chat` модель видит обе предыдущие
пары `user`/`assistant`. Это закрывает корневую причину «новая сессия на
каждое сообщение» (см. `_docs/memory.md` §2.4).

Сетевых вызовов нет: LLM мокается, Executor собирается напрямую.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents.executor import Executor
from app.core.orchestrator import handle_user_task
from app.services.conversation import ConversationStore


@dataclass
class _FakeSettings:
    agent_max_steps: int = 5
    agent_max_output_chars: int = 8000
    agent_max_context_chars: int = 8000
    ollama_default_model: str = "qwen3.5:4b"


class _FakeLLM:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages, *, model: str) -> str:
        self.calls.append([dict(m) for m in messages])
        return self._replies.pop(0)


class _FakeTools:
    def list_descriptions(self):
        return []

    async def execute(self, *args, **kwargs):  # pragma: no cover - не вызывается
        raise AssertionError("tools must not be called in this test")


class _FakePrompts:
    def render_agent_system(self, *, tools_description: str, skills_description: str):
        return "SYSTEM"


class _FakeSkills:
    def list_descriptions(self):
        return []


async def test_three_turn_dialog_keeps_history_across_calls() -> None:
    user_id = 42
    chat_id = 100

    llm = _FakeLLM(
        [
            json.dumps({"final_answer": "Привет, Радиф"}),
            json.dumps({"final_answer": "Тебя зовут Радиф"}),
            json.dumps({"final_answer": "Ты сказал, что тебя зовут Радиф"}),
        ]
    )
    conversations = ConversationStore(max_messages=50)
    executor = Executor(
        settings=_FakeSettings(),
        llm=llm,
        tools=_FakeTools(),
        prompts=_FakePrompts(),
        skills=_FakeSkills(),
    )

    async def turn(text: str) -> str:
        # Имитируем поведение Telegram-handler'а: сначала пишем
        # user-сообщение в стор, затем зовём core.
        conversations.add_user_message(user_id, text)
        reply = await handle_user_task(
            text,
            user_id=user_id,
            chat_id=chat_id,
            conversations=conversations,
            executor=executor,
        )
        conversations.add_assistant_message(user_id, reply)
        return reply

    assert await turn("Привет, я Радиф") == "Привет, Радиф"
    assert await turn("Как меня зовут?") == "Тебя зовут Радиф"
    assert await turn("Что я говорил?") == "Ты сказал, что тебя зовут Радиф"

    # На третьем вызове LLM messages = [system] + 4 предыдущих сообщения
    # (две пары) + текущий user "Что я говорил?".
    third_messages = llm.calls[2]
    assert third_messages[0]["role"] == "system"
    assert third_messages[1:] == [
        {"role": "user", "content": "Привет, я Радиф"},
        {"role": "assistant", "content": "Привет, Радиф"},
        {"role": "user", "content": "Как меня зовут?"},
        {"role": "assistant", "content": "Тебя зовут Радиф"},
        {"role": "user", "content": "Что я говорил?"},
    ]
