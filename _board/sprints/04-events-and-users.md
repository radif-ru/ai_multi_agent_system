# Спринт 04. Событийная модель и модуль Users

- **Источник:** ТЗ пользователя «Эволюция архитектуры приложения»
- **Ветка:** `feature/04-events-and-users` (от `main`; см. `process.md` §2, п.2).
- **Открыт:** 2026-05-05
- **Закрыт:** —

## 1. Цель спринта

Снизить связность между адаптером (Telegram/консоль) и сервисами памяти/истории за счёт перехода на простую in-memory событийную шину, и явно выделить модуль «пользователи» — сейчас идентификация размазана по `telegram_id`, а `UserSettingsRegistry` хранит только per-user оверрайды, без понятия «профиль пользователя». Это подготавливает почву для дополнительных адаптеров (web, MAX) с не-телеграмными идентификаторами и делает цепочку «пришло сообщение → история → суммаризация → очистка tmp» декларативной через подписчиков, а не императивной в хендлере.

Спринт сознательно ограничен MVP-объёмом событийной модели: только in-memory `EventBus`, без очередей, брокеров и персистентности. Архивирование (`/new`) остаётся синхронной операцией с возвратом результата — в событие выносится только **факт завершения** для подписчиков-сайд-эффектов (чистка tmp-картинок).

## 2. Скоуп и non-goals

### В скоупе
- Новый модуль `app/users/` с `User` (dataclass) и `UserRepository` (in-memory) — минимальный контракт «получить/создать пользователя по внешнему id».
- Интеграция `UserRepository` в DI (`app/main.py`, `app/console_main.py`) и в обработчики (Telegram, консоль) — получение/создание пользователя на входе апдейта.
- Новый модуль `app/core/events.py` с `EventBus` (async pub/sub, in-memory) и базовым `Event`.
- События: `UserCreated`, `MessageReceived`, `ResponseGenerated`, `ConversationArchived`.
- Перевод записи истории (`ConversationStore.add_user_message` / `add_assistant_message`) и in-session суммаризации на подписчиков событий `MessageReceived` / `ResponseGenerated`.
- `Archiver` публикует `ConversationArchived` по завершении; `_cleanup_tmp_images` становится подписчиком этого события.
- Unit-тесты на `EventBus`, `UserRepository`, на подписчиков истории/суммаризатора/cleanup.
- Документация: `_docs/architecture.md` (§3 и §4 — описание шины и модуля Users), новый `_docs/events.md` с контрактом событий, обновление `_docs/roadmap.md` и `_docs/current-state.md`.

### Вне скоупа (non-goals)
- Внешние брокеры (Kafka/RabbitMQ/Redis Streams) — прямо запрещены TЗ.
- Персистентность пользователей в БД — `UserRepository` остаётся in-memory в этом спринте.
- Перевод архивирования (`/new`) целиком на события (request/response через шину) — сознательно не делаем, см. §1.
- Аутентификация, авторизация, роли — не этот спринт.
- Замена `UserSettingsRegistry` на БД или вытеснение его целиком — только переключение ключа с `telegram_id` на внутренний `user.id` там, где уместно (и то — опционально, см. задачу 1.2).
- Изменение агентного цикла и контракта tools.

## 3. Acceptance Criteria спринта

- [ ] В коде есть модуль `app/users/` с `User` и `UserRepository`; на каждый входящий апдейт (Telegram, консоль) пользователь гарантированно получен/создан через репозиторий, публикуется `UserCreated` при первой встрече.
- [ ] В коде есть `app/core/events.py` с `EventBus` (async `subscribe` / `publish`), покрытый unit-тестами (порядок вызова подписчиков, изоляция ошибок подписчика, отсутствие блокировок при отсутствии подписчиков).
- [ ] Хендлер текстовых сообщений (`app/adapters/telegram/handlers/messages.py` и его консольный аналог) **не вызывает** напрямую `ConversationStore.add_*` и `Summarizer.summarize` для in-session суммаризации — эти действия выполняются подписчиками событий `MessageReceived` / `ResponseGenerated`.
- [ ] `Archiver.archive` возвращает результат синхронно (как сейчас), **и дополнительно** публикует `ConversationArchived` в конце успешного прогона; `_cleanup_tmp_images` вызывается из подписчика на это событие, а не из хендлера `/new`.
- [ ] `pytest -q` зелёный; добавлены тесты на `EventBus`, `UserRepository`, на подписчиков истории/суммаризатора/cleanup.
- [ ] `_docs/events.md` создан, `_docs/architecture.md` обновлён (описание шины и модуля Users), `_docs/roadmap.md` и `_docs/current-state.md` актуализированы.
- [ ] Все задачи спринта — `Done`, сводная таблица актуальна.

## 4. Этап 1. Модуль Users

Выделить явный модуль «пользователи» с минимальным контрактом, чтобы дальше было куда публиковать `UserCreated` и чтобы не было соблазна размазывать логику по адаптерам.

### Задача 1.1. Создать `app/users/` с `User` и `UserRepository`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §3 (компоненты), `_docs/instructions.md` §3 (стиль).
- **Затрагиваемые файлы:** `app/users/__init__.py`, `app/users/models.py`, `app/users/repository.py`, `tests/users/__init__.py`, `tests/users/test_repository.py`.

#### Описание

Создать модуль с дата-классом `User` и in-memory репозиторием. Репозиторий — единственная точка «получить или создать» пользователя по внешнему ключу (`channel`, `external_id`), где `channel ∈ {"telegram", "console"}`.

1. `User`: `id: int` (внутренний автоинкремент), `channel: str`, `external_id: str`, `display_name: str | None`, `created_at: datetime`.
2. `UserRepository`:
   - `async get_or_create(channel: str, external_id: str, display_name: str | None = None) -> tuple[User, bool]` — возвращает `(user, created)`, где `created=True`, если пользователь создан прямо сейчас.
   - `async get(user_id: int) -> User | None`.
   - `async get_by_external(channel: str, external_id: str) -> User | None`.
3. Потокобезопасность: один `asyncio.Lock` на всю запись (объёмы малы, пуллы не нужны).
4. **Никаких событий** в этой задаче — `UserCreated` публикуется позже, в этапе 2.

#### Definition of Done

- [x] Файлы созданы, импорт `from app.users import User, UserRepository` работает.
- [x] Unit-тест `tests/users/test_repository.py` покрывает: создание нового, повторный `get_or_create` возвращает тот же id и `created=False`, `get_by_external` находит созданного, `get` по несуществующему id — `None`.
- [x] **Документация обновлена**: `_docs/architecture.md` §3 — новый подраздел про модуль Users (короткий, 5–10 строк). До коммита кода.
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист, артефакты не закоммичены.

### Задача 1.2. Интеграция `UserRepository` в адаптеры и DI

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/architecture.md` §3.1 (точка входа), §3.12 (Telegram-адаптер), `_docs/console-adapter.md`.
- **Затрагиваемые файлы:** `app/main.py`, `app/console_main.py`, `app/adapters/telegram/handlers/messages.py`, `app/adapters/telegram/handlers/commands.py`, `app/adapters/console/` (входная точка чтения команды), `app/commands/context.py`, тесты.

#### Описание

Поднять `UserRepository` как долгоживущий сервис в точках входа (`main.py`, `console_main.py`) и прокинуть через `dispatcher["users"]` (aiogram) и через контекст команд консоли. На каждом входящем сообщении **до** обращения к `core.handle_user_task` вызывать `get_or_create` и использовать `user.id` как ключ там, где это не ломает существующее поведение (прежде всего — для будущих событий). На этом этапе **не переписываем** `ConversationStore` и `UserSettingsRegistry` на внутренний id — пусть они продолжают жить на `telegram_id` / `external_id` (смена ключа — вне скоупа, см. §2). Цель задачи — только завести `user` в хендлерах и сделать его доступным для публикации событий в этапе 2.

1. Создать `UserRepository` в точках входа.
2. Прокинуть в `dispatcher["users"]` и в `CommandContext` консоли.
3. В `messages.py::handle_text`, `handle_document`, `handle_voice`, `handle_photo` и в точке ввода консоли — вызвать `get_or_create(...)` в начале и передать `user` дальше (пока — просто в локальную переменную).

#### Definition of Done

- [x] В хендлерах и в консольной точке ввода `user` получается через `UserRepository.get_or_create` до вызова `core.handle_user_task`.
- [x] `pytest -q` зелёный; добавлен/обновлён тест на то, что `UserRepository` действительно вызывается при апдейте (через мок или через smoke-тест handler'а).
- [x] **Документация обновлена**: `_docs/architecture.md` §3.1 и §3.13 — короткое упоминание, что адаптеры обязаны получать пользователя через репозиторий.
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист.

## 5. Этап 2. Событийная шина и перевод истории на события

In-memory шина с async pub/sub. Фундаментальное событие — `MessageReceived` / `ResponseGenerated`. Запись в `ConversationStore` и in-session суммаризация становятся подписчиками, хендлер худеет.

### Задача 2.1. Реализовать `EventBus` и базовый `Event`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** новый `_docs/events.md`.
- **Затрагиваемые файлы:** `app/core/events.py`, `tests/core/test_events.py`.

#### Описание

Минимальная реализация:

1. `Event` — базовый dataclass, у всех наследников — `event_type: ClassVar[str]`.
2. `EventBus`:
   - `subscribe(event_type: type[Event], handler: Callable[[Event], Awaitable[None]]) -> None`.
   - `async publish(event: Event) -> None` — последовательно вызывает всех подписчиков **данного конкретного** типа; исключение подписчика логируется как `WARNING` и **не прерывает** других подписчиков и публикатора.
   - Без wildcard-подписок, без приоритетов, без отмены подписки — явно и скучно.
3. Логирование: `INFO` на каждую публикацию с именем события и числом подписчиков.

#### Definition of Done

- [x] `app/core/events.py` создан; `EventBus` и `Event` экспортируются.
- [x] Unit-тесты покрывают: порядок вызова подписчиков (FIFO регистрации), изоляцию ошибки одного подписчика, публикацию без подписчиков (не падает), типизированный match только по точному типу.
- [x] **Документация обновлена**: создан `_docs/events.md` со стартовым содержанием (назначение, контракт `Event`/`EventBus`, список событий-заготовок на этот спринт).
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист.

### Задача 2.2. События `MessageReceived` / `ResponseGenerated` и `UserCreated`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 2.1, Задача 1.2
- **Связанные документы:** `_docs/events.md`.
- **Затрагиваемые файлы:** `app/core/events.py` (доменные классы событий), `app/users/repository.py`, `app/adapters/telegram/handlers/messages.py`, `app/adapters/console/` (входная точка), `tests/users/test_repository.py`, `tests/adapters/*`.

#### Описание

Ввести доменные события и начать их публиковать — **но пока без подписчиков**, чтобы можно было отдельной задачей перенести логику.

1. `UserCreated(user: User)` — публикуется `UserRepository`-ем (через внедрённый `EventBus`), когда `get_or_create` реально создал пользователя.
2. `MessageReceived(user: User, text: str, conversation_id: str, channel: str)` — публикуется хендлером при входящем тексте (и аналогично — в консоли) после получения `user`.
3. `ResponseGenerated(user: User, text: str, conversation_id: str, channel: str)` — публикуется хендлером **после** получения ответа от `core.handle_user_task`, **до** отправки пользователю.
4. `UserRepository` принимает `EventBus` опциональным аргументом конструктора; если не передан — события не публикуются (важно для юнит-тестов репозитория).

> На этой задаче запись в `ConversationStore` и суммаризация **остаются** в хендлере, как сейчас. Их перенос — в задачах 2.3 и 2.4.

#### Definition of Done

- [x] События определены и публикуются в указанных точках.
- [x] Unit-тест: `UserRepository.get_or_create` с подключённой шиной публикует `UserCreated` ровно один раз на нового пользователя.
- [x] Unit/интеграционный тест на хендлер текста: при входящем апдейте публикуется `MessageReceived`, после ответа — `ResponseGenerated` (через тест-шпион-подписчика).
- [x] **Документация обновлена**: `_docs/events.md` — добавлены контракты всех трёх событий (поля, семантика, кто публикует, кто подписан на MVP).
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист.

### Задача 2.3. Перенести запись в `ConversationStore` на подписчик

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 2.2
- **Связанные документы:** `_docs/memory.md` §2, `_docs/events.md`.
- **Затрагиваемые файлы:** `app/services/conversation.py` (или новый `app/services/conversation_subscriber.py`), `app/main.py`, `app/console_main.py`, `app/adapters/telegram/handlers/messages.py`, `app/adapters/console/`, тесты.

#### Описание

Завести подписчика, который на `MessageReceived` дописывает сообщение пользователя в `ConversationStore`, а на `ResponseGenerated` — ответ ассистента. Соответствующие прямые вызовы из хендлеров удалить. Подписчик регистрируется один раз на старте приложения.

Важно: порядок событий в хендлере остаётся прежним (публикация `MessageReceived` идёт **до** `core.handle_user_task`, публикация `ResponseGenerated` — **после**), чтобы `core.handle_user_task` видел в `ConversationStore` уже актуальное user-сообщение.

#### Definition of Done

- [x] В `messages.py` (Telegram) и в консольной точке ввода **нет** прямых вызовов `conversations.add_user_message` / `conversations.add_assistant_message` в основном потоке обработки текста.
- [x] Подписчик покрыт unit-тестом: публикация `MessageReceived` приводит к `add_user_message`, `ResponseGenerated` — к `add_assistant_message` с корректными ключами.
- [x] Существующие тесты хендлеров продолжают проходить (или адаптированы).
- [x] **Документация обновлена**: `_docs/memory.md` §2 и `_docs/architecture.md` §4 — упомянуть, что запись в `ConversationStore` теперь идёт через подписчика на события.
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист.

### Задача 2.4. Перенести in-session суммаризацию на подписчик

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 2.3
- **Связанные документы:** `_docs/memory.md` §2.5, `_docs/architecture.md` §4 пункт 8.2.
- **Затрагиваемые файлы:** `app/services/summarizer.py` или новый `app/services/summarizer_subscriber.py`, `app/adapters/telegram/handlers/messages.py`, `app/adapters/console/`, `app/main.py`, `app/console_main.py`, тесты.

#### Описание

Текущую логику «если `len(history) >= history_summary_threshold` после записи ответа — сожми историю и положи через `replace_with_summary`» оформить отдельным подписчиком на `ResponseGenerated`. Подписчик регистрируется **после** подписчика из задачи 2.3 (чтобы к моменту суммаризации ответ уже был записан в стор), порядок гарантируется порядком регистрации.

Поведение остаётся прежним:
- Падение суммаризации — `WARNING`, не прерывает обработку других подписчиков и не ломает публикатора (уже обеспечено `EventBus`, см. задачу 2.1).
- Подписчик-суммаризатор **не** держит пользовательского ответа — он работает после того, как хендлер уже отправил ответ пользователю (суммаризация идёт в фоне относительно UX).

#### Definition of Done

- [x] В хендлере текста нет вызова `summarizer.summarize(...)` в основном потоке.
- [x] Unit-тест: `ResponseGenerated` при `history_len >= threshold` приводит к вызову `Summarizer.summarize` и `replace_with_summary`; при меньшей длине — не приводит.
- [x] Unit-тест: исключение в суммаризаторе не роняет других подписчиков (через тест-шпион).
- [x] **Документация обновлена**: `_docs/memory.md` §2.5 — уточнить, что триггер in-session суммаризации — подписчик на `ResponseGenerated`.
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист.

## 6. Этап 3. Событие `ConversationArchived` и вынос tmp-cleanup

Архивирование `/new` остаётся синхронной операцией с возвратом результата пользователю. Но **факт завершения** публикуется как событие, и очистка tmp-картинок уезжает из хендлера в подписчик.

### Задача 3.1. `Archiver` публикует `ConversationArchived`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Задача 2.1
- **Связанные документы:** `_docs/memory.md`, `_docs/architecture.md` §5.
- **Затрагиваемые файлы:** `app/services/archiver.py`, `app/core/events.py`, `tests/services/test_archiver.py`.

#### Описание

1. Определить `ConversationArchived(user: User, conversation_id: str, chunks: int, channel: str)` в `app/core/events.py`.
2. `Archiver` получает `EventBus` опциональным параметром конструктора.
3. В конце **успешного** прогона `Archiver.archive` публикуется `ConversationArchived`. При неуспехе — не публикуется (поведение как сейчас: история не очищается, пользователь видит ошибку).

Контракт `Archiver.archive` — **не меняется**: он по-прежнему возвращает число чанков и принимает `progress_callback`. Никакой request/response через шину.

#### Definition of Done

- [x] Событие опубликовано ровно один раз на успешное архивирование; при падении — не публикуется.
- [x] Unit-тест: успешный `archive` публикует `ConversationArchived` с корректными полями; упавший — не публикует.
- [x] **Документация обновлена**: `_docs/events.md` — добавлен контракт `ConversationArchived`; `_docs/memory.md` — короткое упоминание.
- [x] **Тесты добавлены / обновлены**: см. выше.
- [x] `git status` чист.

### Задача 3.2. Вынести `_cleanup_tmp_images` в подписчика `ConversationArchived`

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/architecture.md` §6.4 (cleanup старых изображений), `_docs/commands.md` (`/new`).
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/commands.py`, новый `app/services/tmp_cleanup.py` (или функция-подписчик в существующем модуле), `app/main.py`, `app/console_main.py`, тесты.

#### Описание

Сейчас `_cleanup_tmp_images` вызывается из хендлера `/new` напрямую. Перенести его в функцию-подписчика на `ConversationArchived`. Регистрация подписчика — в точке входа. Хендлер `/new` перестаёт знать про tmp-очистку.

#### Definition of Done

- [ ] В хендлере `/new` нет вызова `_cleanup_tmp_images`; соответствующий код удалён.
- [ ] Unit-тест: публикация `ConversationArchived` триггерит cleanup (с учётом TTL 1 час — как сейчас); при успешном `archive` без реального вызова хендлера — cleanup всё равно отработает, если явно опубликовать событие.
- [ ] Smoke-проверка в консольном/Telegram-режиме: после `/new` старые изображения удаляются (если воспроизводимо в тестовом прогоне — автотест; иначе — ручной чек, отмеченный в `_board/progress.txt`).
- [ ] **Документация обновлена**: `_docs/architecture.md` §6.4 и `_docs/commands.md` — уточнить, что cleanup — подписчик на событие, не часть хендлера.
- [ ] **Тесты добавлены / обновлены**: см. выше.
- [ ] `git status` чист.

## 7. Этап 4. Документация и закрытие

### Задача 4.1. Финальная ревизия документации и `current-state.md` / `roadmap.md`

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Задача 3.2
- **Связанные документы:** `_docs/events.md`, `_docs/architecture.md`, `_docs/current-state.md`, `_docs/roadmap.md`.
- **Затрагиваемые файлы:** `_docs/*.md`, `_board/plan.md`, `_board/progress.txt`.

#### Описание

Пройтись по документам ещё раз после всех кодовых коммитов:

1. `_docs/events.md` — финальный состав событий и подписчиков на конец спринта (таблица «кто публикует / кто подписан»).
2. `_docs/architecture.md` — обновить схему §1 (добавить `EventBus` и `UserRepository` как долгоживущие сервисы), §4 (упомянуть события в потоке текстового сообщения), §5 (упомянуть `ConversationArchived` в потоке `/new`).
3. `_docs/current-state.md` §1 — записи о новом модуле Users и событийной шине; §3 — архитектурный нюанс про гарантии порядка подписчиков (FIFO регистрации).
4. `_docs/roadmap.md` — пометить соответствующий этап/подэтап.
5. `_board/plan.md` — передвинуть спринт 04 из «Запланированные» в «Закрытые» при финальном закрытии.

#### Definition of Done

- [ ] Все упомянутые документы актуализированы единым `docs(...)`-коммитом (или серией).
- [ ] `grep -rn "add_user_message\|add_assistant_message" _docs/` не возвращает устаревших упоминаний о прямом вызове из хендлеров.
- [ ] **Документация обновлена**: см. выше (задача чисто-документационная; тесты — `n/a`).
- [ ] **Тесты добавлены / обновлены**: `n/a` — чисто-документационная задача.
- [ ] `git status` чист.

## 8. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | Смена порядка операций в хендлере (запись в стор → вызов core → ответ) может сломать `core.handle_user_task`, который рассчитывает, что user-сообщение уже в `ConversationStore`. | Порядок публикаций сохраняется: `MessageReceived` публикуется **до** вызова core, `ResponseGenerated` — **после**. Подписчик на `MessageReceived` синхронно пишет в стор (шина вызывает подписчиков через `await`), так что к моменту вызова core сообщение уже в сторе. Это покрыто тестом задачи 2.3. |
| 2 | Исключение в одном подписчике незаметно проглатывается. | `EventBus` логирует исключения подписчиков как `WARNING` со стэктрейсом; тест задачи 2.1 явно проверяет, что ошибка не ломает других. В `_docs/events.md` отдельно зафиксирован контракт «подписчики изолированы». |
| 3 | Соблазн «переписать /new полностью на события». | В §2 явно вынесено в non-goals; в §1 дано объяснение. В задаче 3.1 контракт `Archiver.archive` зафиксирован как неизменный. |
| 4 | Лишний `UserRepository` усложнит код без пользы, если не вытаскивать на него `ConversationStore`. | В этом спринте репозиторий — минимальный (in-memory, без БД); от него требуется только публиковать `UserCreated` и предоставить `user` хендлерам для событий. Вытеснение ключей `ConversationStore` — отдельный будущий спринт (или вовсе не нужно). |
| 5 | Тесты хендлеров начнут зависеть от инициализации шины — рост boilerplate. | Завести хелпер-фикстуру `event_bus_with_defaults` в `tests/conftest.py` или в `tests/core/conftest.py`; подключать её только там, где она реально нужна. |

## 9. Сводная таблица задач спринта

| #   | Задача                                                                 | Приоритет | Объём | Статус | Зависит от |
|-----|------------------------------------------------------------------------|:---------:|:-----:|:------:|:----------:|
| 1.1 | Создать `app/users/` с `User` и `UserRepository`                       | high      | S     | Done    | —          |
| 1.2 | Интеграция `UserRepository` в адаптеры и DI                            | high      | S     | Done    | 1.1        |
| 2.1 | Реализовать `EventBus` и базовый `Event`                               | high      | S     | Done    | —          |
| 2.2 | События `MessageReceived` / `ResponseGenerated` / `UserCreated`        | high      | S     | Done    | 2.1, 1.2   |
| 2.3 | Перенести запись в `ConversationStore` на подписчик                    | high      | S     | Done   | 2.2        |
| 2.4 | Перенести in-session суммаризацию на подписчик                         | medium    | S     | Done   | 2.3        |
| 3.1 | `Archiver` публикует `ConversationArchived`                            | medium    | XS    | Done   | 2.1        |
| 3.2 | Вынести `_cleanup_tmp_images` в подписчика `ConversationArchived`      | medium    | XS    | ToDo   | 3.1        |
| 4.1 | Финальная ревизия документации и `current-state.md` / `roadmap.md`     | medium    | XS    | ToDo   | 3.2        |

> Обновляется при каждом переходе статуса и при добавлении/удалении задач.

## 10. История изменений спринта

- **2026-05-05** — спринт открыт, ветка `feature/04-events-and-users` создана от `main`.
- **2026-05-05** — закрыта задача 1.1: создан модуль users с User и UserRepository, добавлены тесты, обновлена документация.
- **2026-05-05** — закрыта задача 1.2: UserRepository интегрирован в точки входа (main.py, console_main.py), прокинут через dispatcher["users"] в Telegram и через CommandContext в консоли, добавлены вызовы get_or_create в хендлерах messages.py и консольной точке ввода, обновлена документация.
- **2026-05-05** — закрыта задача 2.1: реализован EventBus и базовый Event, добавлены unit-тесты, создана документация _docs/events.md.
- **2026-05-05** — закрыта задача 2.2: добавлена публикация событий UserCreated (в UserRepository), MessageReceived и ResponseGenerated (в хендлерах Telegram и консоли), EventBus интегрирован в DI (main.py, console_main.py), обновлена документация _docs/events.md с контрактами событий.
- **2026-05-05** — закрыта задача 2.3: создан conversation_subscriber.py с подписчиками MessageReceived и ResponseGenerated для записи в ConversationStore, подписчики зарегистрированы в main.py и console_main.py, удалены прямые вызовы add_user_message/add_assistant_message из хендлеров Telegram и консоли, обновлена документация _docs/events.md, обновлены тесты для работы с новой архитектурой.
- **2026-05-05** — закрыта задача 2.4: создан summarizer_subscriber.py с подписчиком on_response_generated_summarize для in-session суммаризации, подписчик зарегистрирован в main.py и console_main.py после conversation_subscriber, удалены прямые вызовы summarizer.summarize из хендлеров Telegram и консоли, добавлены unit-тесты, обновлена документация _docs/memory.md §2.5.
- **2026-05-05** — закрыта задача 3.1: добавлено событие ConversationArchived в events.py, Archiver принимает EventBus опциональным параметром и публикует событие при успешном архивировании, добавлены поля user и channel в CommandContext, обновлены точки входа (main.py, console_main.py) и хендлеры для передачи user/channel в archiver.archive(), добавлены unit-тесты для проверки публикации события, обновлена документация _docs/memory.md.
