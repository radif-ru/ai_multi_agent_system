"""Подписчики событий для записи в DialogJournal.

Пишут каждое текстовое сообщение пользователя/ассистента в append-only
журнал `dialog_journal` (`data/memory.db`). См. `_docs/memory.md` §4 и
задачу 3.2 спринта 06.

`conversation_id`, который в журнале — это **внутренний UUID сессии** из
`ConversationStore.current_conversation_id(...)`, ротируемый при `/new`
и `/reset`. В событиях `MessageReceived/ResponseGenerated` поле
`event.conversation_id` исторически содержит `chat_id` — это значение
кладётся в столбец `chat_id` журнала (нейминг в событиях не трогаем,
чтобы не ломать существующие подписчики).

Ошибки записи в журнал логируются как WARNING и не валят основной
поток обработки сообщения (RTM > consistency: лучше потерять одну
строку журнала, чем обвалить ответ пользователю).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.events import MessageReceived, ResponseGenerated
    from app.services.conversation import ConversationStore
    from app.services.dialog_journal import DialogJournal

logger = logging.getLogger(__name__)


def _resolve_user_id(external_id: str) -> int:
    """Преобразовать `User.external_id` в `int`-ключ сторов.

    Совпадает с конвенцией существующего `conversation_subscriber`.
    Падает с `ValueError`, если `external_id` нечисловой — это сигнал,
    что канал не Telegram/console и нужен явный мэппинг.
    """
    return int(external_id)


async def on_message_received_journal(
    event: "MessageReceived",
    *,
    conversations: "ConversationStore",
    journal: "DialogJournal",
) -> None:
    """Записать пользовательское сообщение в `dialog_journal`."""
    try:
        user_id = _resolve_user_id(event.user.external_id)
        chat_id = int(event.conversation_id)
        cid = conversations.current_conversation_id(user_id)
        await journal.append(
            user_id=user_id,
            chat_id=chat_id,
            conversation_id=cid,
            role="user",
            kind="text",
            content=event.text,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dialog_journal: не удалось записать MessageReceived: %s", exc)


async def on_response_generated_journal(
    event: "ResponseGenerated",
    *,
    conversations: "ConversationStore",
    journal: "DialogJournal",
) -> None:
    """Записать ответ ассистента в `dialog_journal`."""
    try:
        user_id = _resolve_user_id(event.user.external_id)
        chat_id = int(event.conversation_id)
        cid = conversations.current_conversation_id(user_id)
        await journal.append(
            user_id=user_id,
            chat_id=chat_id,
            conversation_id=cid,
            role="assistant",
            kind="text",
            content=event.text,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dialog_journal: не удалось записать ResponseGenerated: %s", exc)
