"""Регрессионный e2e: имя пользователя переживает `/new`.

Закрывает корневой баг спринта 02 / Этап 4 (см. `_docs/current-state.md`
§2.1, `_docs/memory.md` §2.5): после длинной сессии с in-session
`replace_with_summary` (которая разрушает `_messages` до summary + last 2)
команда `/new` должна архивировать ПОЛНЫЙ лог сессии (`_session_log`), а
не усечённую `get_history()`. После `/new` ранние факты (имя «Радиф»)
должны находиться авто-подгрузкой `SessionBootstrap` в новой сессии.

Сетевых вызовов нет: `OllamaClient.chat` / `embed` мокаются, а
`SemanticMemory` заменяется in-memory фейком, поддерживающим `insert` /
`search` / `delete`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.archiver import Archiver
from app.services.conversation import ConversationStore
from app.services.llm import OllamaClient
from app.services.session_bootstrap import build_bootstrap_message
from app.services.summarizer import Summarizer


@dataclass
class _FakeSettings:
    embedding_model: str = "nomic-embed-text"
    session_bootstrap_enabled: bool = True
    session_bootstrap_top_k: int = 3


class _FakeMemory:
    """In-memory заглушка `SemanticMemory` с поиском по подстроке."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._next_id = 1

    async def insert(self, text, embedding, metadata):
        rowid = self._next_id
        self._next_id += 1
        self.rows.append(
            {
                "rowid": rowid,
                "text": text,
                "embedding": embedding,
                "metadata": dict(metadata),
            }
        )
        return rowid

    async def delete(self, rowid):
        self.rows = [r for r in self.rows if r["rowid"] != rowid]

    async def search(self, embedding, *, top_k, scope_user_id):
        # Поиска по эмбеддингу нет — для теста достаточно вернуть все
        # чанки пользователя в порядке вставки. Промпт `SessionBootstrap`
        # требует, чтобы среди них была релевантная часть.
        rows = [
            {"text": r["text"], "distance": 0.0}
            for r in self.rows
            if r["metadata"]["user_id"] == scope_user_id
        ]
        return rows[:top_k]


@pytest.mark.asyncio
async def test_name_survives_new_command_and_is_loaded_in_next_session(mocker):
    user_id = 42
    chat_id = 777

    # 1) Имитируем длинную сессию с ранней репликой про имя.
    conversations = ConversationStore(max_messages=10, session_log_max_messages=1000)
    conversations.add_user_message(user_id, "Привет, я Радиф")
    conversations.add_assistant_message(user_id, "Привет, Радиф")
    for i in range(8):
        conversations.add_user_message(user_id, f"u{i}")
        conversations.add_assistant_message(user_id, f"a{i}")

    # 2) In-session compaction: имя из get_history исчезает.
    conversations.replace_with_summary(user_id, "сжатое резюме", kept_tail=2)
    assert not any(
        "Радиф" in m["content"] for m in conversations.get_history(user_id)
    ), "регрессия: get_history теряет имя — это и есть исходный баг"
    # А _session_log — нет.
    full_log = conversations.get_session_log(user_id)
    assert any("Радиф" in m["content"] for m in full_log)

    # 3) Архивация (то, что делает cmd_new): моки Summarizer и embed.
    llm = OllamaClient(base_url="http://localhost:11434", timeout=10.0)
    summarizer = Summarizer(llm=llm, system_prompt="SYS", chunk_messages=30)

    captured_input: dict = {}

    async def fake_summarize(messages, *, model, temperature=0.0):
        captured_input["messages"] = list(messages)
        # Резюме явно сохраняет имя — как требует усиленный промпт.
        return "Пользователь представился: меня зовут Радиф. Обсуждали u0..u7."

    mocker.patch.object(summarizer, "summarize", side_effect=fake_summarize)
    mocker.patch.object(llm, "embed", return_value=[0.1, 0.2, 0.3])

    memory = _FakeMemory()
    archiver = Archiver(
        llm=llm,
        summarizer=summarizer,
        semantic_memory=memory,
        summarizer_model="qwen3.5:4b",
        embedding_model="nomic-embed-text",
        chunk_size=1500,
        chunk_overlap=150,
    )

    # cmd_new передаёт `get_session_log`, а не `get_history` — это и есть
    # фикс из задачи 4.3.
    inserted = await archiver.archive(
        conversations.get_session_log(user_id),
        conversation_id=conversations.current_conversation_id(user_id),
        user_id=user_id,
        chat_id=chat_id,
    )
    assert inserted >= 1

    # 4) Полный лог уехал в Summarizer — имя там есть.
    assert any("Радиф" in m["content"] for m in captured_input["messages"])
    # И в архиве есть чанк с именем.
    assert any("Радиф" in r["text"] for r in memory.rows)
    # Эмулируем `cmd_new`: clear + rotate.
    conversations.clear(user_id)

    # 5) Новая сессия: первый запрос должен подтянуть архив.
    conversations.add_user_message(user_id, "Как меня зовут?")
    settings = _FakeSettings()
    msg = await build_bootstrap_message(
        query="Как меня зовут?",
        user_id=user_id,
        settings=settings,
        llm=llm,
        semantic_memory=memory,
    )
    assert msg is not None
    assert msg["role"] == "system"
    assert "Радиф" in msg["content"]
