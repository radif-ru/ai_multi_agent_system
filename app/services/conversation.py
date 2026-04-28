"""Краткосрочная память: in-memory история диалога per-user.

См. `_docs/memory.md` §2 и `_docs/architecture.md` §3.5.
"""

from __future__ import annotations

import uuid
from typing import Any


Message = dict[str, Any]


class ConversationStore:
    """In-memory история сообщений и conversation_id для каждого пользователя."""

    def __init__(self, *, max_messages: int) -> None:
        if max_messages <= 0:
            raise ValueError("max_messages must be > 0")
        self._max_messages = max_messages
        self._messages: dict[int, list[Message]] = {}
        self._conversation_ids: dict[int, str] = {}

    # -- история ----------------------------------------------------------

    def get_history(self, user_id: int) -> list[Message]:
        """Вернуть копию истории; внешние мутации не влияют на стор."""
        return [dict(m) for m in self._messages.get(user_id, [])]

    def add_user_message(self, user_id: int, text: str) -> None:
        self._append(user_id, {"role": "user", "content": text})

    def add_assistant_message(self, user_id: int, text: str) -> None:
        self._append(user_id, {"role": "assistant", "content": text})

    def add_system_message(self, user_id: int, text: str) -> None:
        self._append(user_id, {"role": "system", "content": text})

    def replace_with_summary(
        self, user_id: int, summary: str, *, kept_tail: int = 2
    ) -> None:
        """Заменить всё, кроме последних kept_tail сообщений, одним system-резюме."""
        if kept_tail < 0:
            raise ValueError("kept_tail must be >= 0")
        history = self._messages.get(user_id, [])
        tail = history[-kept_tail:] if kept_tail else []
        summary_msg: Message = {
            "role": "system",
            "content": f"Краткое резюме предыдущей части диалога: {summary}",
        }
        self._messages[user_id] = [summary_msg, *tail]

    def clear(self, user_id: int) -> None:
        self._messages.pop(user_id, None)
        self._conversation_ids.pop(user_id, None)

    # -- conversation_id --------------------------------------------------

    def current_conversation_id(self, user_id: int) -> str:
        cid = self._conversation_ids.get(user_id)
        if cid is None:
            cid = uuid.uuid4().hex
            self._conversation_ids[user_id] = cid
        return cid

    def rotate_conversation_id(self, user_id: int) -> str:
        """Сгенерировать новый conversation_id; вернуть старый (или пустую строку)."""
        old = self._conversation_ids.get(user_id, "")
        self._conversation_ids[user_id] = uuid.uuid4().hex
        return old

    # -- internals --------------------------------------------------------

    def _append(self, user_id: int, msg: Message) -> None:
        bucket = self._messages.setdefault(user_id, [])
        bucket.append(msg)
        overflow = len(bucket) - self._max_messages
        if overflow > 0:
            del bucket[:overflow]
