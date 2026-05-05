# Событийная шина (EventBus)

## Назначение

Событийная шина реализует асинхронный pub/sub механизм для обмена событиями между компонентами приложения. Это позволяет развязать компоненты и перевести побочные эффекты (запись в историю, суммаризацию, очистку временных файлов) на подписчиков событий.

## Контракт

### Event

Базовый класс для всех событий:

```python
from dataclasses import dataclass
from typing import ClassVar

@dataclass
class Event:
    event_type: ClassVar[str] = "base"
```

Все события должны:
- Наследоваться от `Event`
- Определять `event_type: ClassVar[str]` для идентификации типа

### EventBus

```python
class EventBus:
    def subscribe(event_type: type[Event], handler: Callable[[Event], Awaitable[None]]) -> None
    async publish(event: Event) -> None
```

- `subscribe(event_type, handler)`: регистрирует асинхронный обработчик для указанного типа события
- `publish(event)`: публикует событие, вызывая всех подписчиков данного типа в порядке регистрации (FIFO)

### Гарантии

- Подписчики вызываются последовательно в порядке регистрации
- Исключение в одном подписчике логируется как `WARNING` и не прерывает других подписчиков или публикатора
- Публикация без подписчиков не падает
- Типизированный match только по точному типу события (без wildcard-подписок)

## События спринта 04

### UserCreated

**Публикуется:** `UserRepository.get_or_create` при реальном создании нового пользователя (не при повторном вызове).

**Поля:**
- `user: User` - созданный пользователь

**Семантика:** Уведомляет о появлении нового пользователя в системе. На текущий момент подписчиков нет (заготовка для будущего).

**Кто публикует:** UserRepository (через внедрённый EventBus)

**Кто подписан (MVP):** никто (заготовка для будущего)


### MessageReceived

**Публикуется:** Хендлеры (Telegram: handle_text, handle_document, handle_voice, handle_photo; консоль: _handle_text) после получения пользователя и перед вызовом `core.handle_user_task`.

**Поля:**
- `user: User` - пользователь, отправивший сообщение
- `text: str` - текст сообщения (для файлов - обогащённый goal с путём к файлу)
- `conversation_id: str` - идентификатор беседы
- `channel: str` - канал ("telegram" или "console")

**Семантика:** Уведомляет о входящем сообщении пользователя. Подписчики записывают сообщение в ConversationStore.

**Кто публикует:** Хендлеры адаптеров (Telegram, консоль)

**Кто подписан (MVP):** conversation_subscriber.on_message_received - записывает сообщение в ConversationStore


### ResponseGenerated

**Публикуется:** Хендлеры (Telegram: handle_text, handle_document, handle_voice, handle_photo; консоль: _handle_text) после получения ответа от `core.handle_user_task` и перед отправкой пользователю.

**Поля:**
- `user: User` - пользователь, получивший ответ
- `text: str` - сгенерированный ответ
- `conversation_id: str` - идентификатор беседы
- `channel: str` - канал ("telegram" или "console")

**Семантика:** Уведомляет о генерации ответа LLM. Подписчики записывают ответ в ConversationStore.

**Кто публикует:** Хендлеры адаптеров (Telegram, консоль)

**Кто подписан (MVP):** conversation_subscriber.on_response_generated - записывает ответ в ConversationStore


### ConversationArchived

**Публикуется:** `Archiver.archive` после успешного завершения архивации сессии.

**Поля:**
- `user: User` - пользователь, инициировавший архивацию
- `conversation_id: str` - идентификатор архивированной беседы
- `chunks: int` - количество заархивированных чанков
- `channel: str` - канал ("telegram" или "console")

**Семантика:** Уведомляет о завершении архивации беседы. Подписчики выполняют побочные эффекты (например, очистку временных файлов).

**Кто публикует:** Archiver (через внедрённый EventBus)

**Кто подписан (MVP):** `on_conversation_archived_cleanup` (tmp_cleanup.py) - удаляет изображения старше 1 часа из временной директории при успешном архивировании
