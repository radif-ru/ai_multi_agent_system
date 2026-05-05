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

Публикуется при первом обнаружении пользователя через `UserRepository.get_or_create`.

### MessageReceived

Публикуется при получении текстового сообщения или файла до вызова `core.handle_user_task`.

### ResponseGenerated

Публикуется после получения ответа от LLM.

### ConversationArchived

Публикуется `Archiver.archive` после успешного завершения архивации сессии.
