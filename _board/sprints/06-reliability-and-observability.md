# Спринт 06. Надёжность диалога и observability

- **Источник:** запрос пользователя (10.05.2026); `_docs/roadmap.md` § «Этап 11. CI», «Этап 17. Очистка существующего техдолга flake8».
- **Ветка:** `feature/06-reliability-and-observability` (от `main`; см. `_board/process.md` §2 п.2).
- **Открыт:** 2026-05-10
- **Закрыт:** —

## 1. Цель спринта

Закрыть три накопившиеся проблемы качества проекта одним связным циклом:

1. **Не теряем диалог при рестарте.** Сейчас `ConversationStore._session_log` живёт только в RAM, и при любом нештатном завершении процесса (краш, kill, рестарт хоста, повторный старт через `python -m app`) полная история сессии исчезает до того, как `/new` успеет её заархивировать. После спринта незаархивированный диалог автоматически перенесётся в `memory_chunks` при следующем старте.
2. **Видим, что происходит.** Логи проекта плоские, без trace_id и без корреляции событий пользователя с ошибками. После спринта появляются структурные JSON-логи с единым `trace_id`, который пробрасывается из обработчика входящего сообщения через все внешние вызовы (LLM, OCR, vision, transcribe, web/http) и до `error tracking` в self-hosted GlitchTip.
3. **Не пропускаем регрессии.** После спринта каждый push/PR прогоняется через `pytest -q` и `flake8` в GitHub Actions; baseline flake8-нарушений (~98) обнулён.

## 2. Скоуп и non-goals

### В скоупе

- Чистка `flake8`-техдолга в `app/` и `tests/`.
- Аудит схем `data/memory.db` и `data/file_contexts.db`: используются ли все поля, корректно ли заполняются; точечная очистка/документирование.
- Новая таблица `dialog_journal` в `data/memory.db` (append-only) и фоновое восстановление при старте.
- Структурное JSON-логирование с `trace_id` (через `contextvars`); включение в ключевых местах кода.
- Интеграция с self-hosted GlitchTip (Sentry-совместимый OSS) через `sentry-sdk`; опциональное включение через `.env` (`SENTRY_DSN`).
- `docker-compose.yml` для запуска GlitchTip рядом с ботом (минимальная конфигурация, инструкция в `_docs/`).
- GitHub Actions workflow: `pytest -q` + `flake8` на push/PR.

### Вне скоупа (non-goals)

- Полный Docker для самого бота (этап 10 roadmap — отдельным спринтом).
- Матрица версий Python в CI и `pytest-cov` (минимальный CI).
- Изменение алгоритма семантического поиска или формата эмбеддингов.
- Webhook-режим (этап 7 roadmap).
- Любые работы по multi-agent, web-адаптеру, MAX-адаптеру.

## 3. Acceptance Criteria спринта

- [ ] `flake8 app tests` — 0 нарушений; `per-file-ignores` в `.flake8` пересмотрены.
- [ ] При краше/рестарте процесса все пользовательские/ассистентские/файловые сообщения, которые не успели попасть в `memory_chunks`, автоматически архивируются при следующем старте.
- [ ] Аудит обеих БД (`memory.db`, `file_contexts.db`) задокументирован; неиспользуемые поля удалены либо явно объяснены в `_docs/memory.md`.
- [ ] Семантический поиск (`MemorySearchTool`) подтверждён сквозным тестом на реальном `sqlite-vec`: `insert → search` с фильтром по `user_id`.
- [ ] Все логи приложения — структурные JSON; в каждой записи присутствуют `timestamp`, `level`, `service`, `trace_id`, `user_id` (если применимо).
- [ ] Один `trace_id` сквозной от приёма сообщения в Telegram до записи об ошибке в GlitchTip; это покрыто тестом и подтверждено вручную на четырёх искусственных сценариях ошибок (ручная, async, внешний сервис, данные).
- [ ] GitHub Actions запускает `pytest` и `flake8` автоматически; пайплайн зелёный на ветке спринта; бейдж в `README.md`.
- [ ] Все задачи спринта — `Done`, сводная таблица актуальна.

## 4. Этап 1. Чистка flake8-техдолга

Закрываем накопленный baseline (~98 нарушений) без рефакторинга соседнего кода: только то, что вернёт `flake8` к нулю.

### Задача 1.1. Закрыть нарушения flake8 в `app/`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/instructions.md` §8.3; `_docs/roadmap.md` § «Этап 17».
- **Затрагиваемые файлы:** `app/**/*.py`.

#### Описание

Прогнать `.venv/bin/python -m flake8 app` и закрыть все нарушения. Ожидается: `F401` (неиспользуемые импорты), `F841` (неиспользуемые локальные переменные), `W293` (пробелы в пустых строках), `E501` (длинные строки), `E741` (имя `l`), `F541`, `F811`, `F821`. Чинить хирургически: удалять только осиротевшие импорты/переменные, не рефакторить соседний код.

#### Definition of Done

- [x] `flake8 app` — 0 нарушений.
- [x] `pytest -q` — зелёный.
- [x] `git diff --stat` показывает только удаления/мелкие правки, никаких рефакторингов.
- [x] **Документация обновлена** — `n/a` (правки не меняют поведение).
- [x] **Тесты добавлены / обновлены** — `n/a`.
- [x] `git status` чист.

### Задача 1.2. Закрыть нарушения flake8 в `tests/`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/instructions.md` §8.3.
- **Затрагиваемые файлы:** `tests/**/*.py`.

#### Описание

То же, что в 1.1, для `tests/`. Дополнительно убрать `import pytest`, если он не используется. Оставить `# noqa` только там, где нарушение осознанно (например, длинная фикстура с тестовыми данными).

#### Definition of Done

- [x] `flake8 tests` — 0 нарушений.
- [x] `pytest -q` — зелёный.
- [x] **Документация обновлена** — `n/a`.
- [x] **Тесты добавлены / обновлены** — `n/a`.
- [x] `git status` чист.

### Задача 1.3. Пересмотреть `per-file-ignores` в `.flake8`

- **Статус:** Done
- **Приоритет:** low
- **Объём:** XS
- **Зависит от:** Задача 1.1, Задача 1.2.
- **Связанные документы:** `_docs/roadmap.md` § «Этап 17» (последний пункт).
- **Затрагиваемые файлы:** `.flake8`.

#### Описание

После закрытия 1.1–1.2 пересмотреть секцию `per-file-ignores`: удалить записи, которые больше не нужны. Если запись остаётся — добавить рядом короткий комментарий, почему она нужна.

#### Definition of Done

- [x] `flake8 app tests` — 0 нарушений.
- [x] В `.flake8` нет «мёртвых» исключений.
- [x] **Документация обновлена** — `n/a`.
- [x] **Тесты добавлены / обновлены** — `n/a`.
- [x] `git status` чист.

## 5. Этап 2. Аудит персистентного слоя

Проверяем, что обе БД используются по назначению и `RAG`-стек собирается end-to-end. Этап завершается до начала работы с журналом — иначе риск построить журнал поверх скрытых багов схемы.

### Задача 2.1. Аудит `data/memory.db`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` §3, §5.
- **Затрагиваемые файлы:** `app/services/memory.py`, `_docs/memory.md` §3, `_docs/current-state.md` §2 (если найдём нюансы).

#### Описание

1. Зафиксировать текущую схему `memory_chunks`: какие поля, какие индексы, чем заполняются (`user_id`, `chat_id`, `conversation_id`, `chunk_index`, `created_at`, `text`).
2. Проверить, что каждое поле реально используется (поиск по коду): `chat_id` — кандидат на проверку, его сейчас нет в `WHERE`-фильтре `_search_sync`.
3. Проверить корректность работы виртуальной таблицы `memory_vec` и связанных служебных (`memory_vec_chunks`, `memory_vec_rowids`, `memory_vec_vector_chunks00`).
4. По итогу — обновить `_docs/memory.md` §3 (актуальная схема + назначение каждого поля). Если найдено лишнее поле — отдельной задачей на удаление, **не** удалять в этой.

#### Definition of Done

- [x] Описание схемы и назначение каждого поля в `_docs/memory.md` соответствует коду.
- [x] Зафиксирован вердикт: можно ли удалить `chat_id` без потери функциональности (или почему он остаётся).
- [x] **Документация обновлена** — да, `_docs/memory.md`.
- [x] **Тесты добавлены / обновлены** — `n/a` (только аудит).
- [x] `git status` чист.

### Задача 2.2. Аудит `data/file_contexts.db`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` §2.6.
- **Затрагиваемые файлы:** `app/services/conversation.py` (только инспекция), `_docs/memory.md` §2.6.

#### Описание

Проверить таблицу `file_contexts`: поля `file_id`, `file_path` оба используются (`save_file_context` пишет, `get_file_context` читает только `context`). Описать, какие поля действительно нужны для текущих сценариев (reply на файл) и какие — задел/мёртвый код.

#### Definition of Done

- [x] В `_docs/memory.md` §2.6 актуальное описание схемы (добавлен §2.6.1 + исправлены расхождения с кодом).
- [x] Если найдено мёртвое поле — запись в `_docs/current-state.md` §2 с предложением удалить отдельной задачей. Мёртвых полей не обнаружено — запись не требуется.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — `n/a`.
- [x] `git status` чист.

### Задача 2.3. Сквозной тест RAG-поиска (`MemorySearchTool` + sqlite-vec)

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 2.1.
- **Связанные документы:** `_docs/memory.md` §3, §5.
- **Затрагиваемые файлы:** `tests/services/test_memory.py` или новый `tests/test_rag_roundtrip.py`.

#### Описание

Если такого теста ещё нет: добавить тест, который на временной БД (`tmp_path`) делает `init → insert(N=3 чанка с разными user_id) → search(top_k=2, scope_user_id=A)` и проверяет: возвращены только чанки `user_id=A`, отсортированы по `distance`. Использовать детерминированные «эмбеддинги» (например, one-hot) — вокруг `nomic-embed-text` обёртку **не дёргать**.

Если тест уже есть в `tests/services/test_memory.py` — задача `n/a`, отметить и закрыть без правки кода.

#### Definition of Done

- [x] `pytest tests/services/test_memory.py -q` — зелёный, есть кейс с фильтром `scope_user_id` (`test_search_orders_by_distance_and_filters_by_user`).
- [x] **Документация обновлена** — `n/a`.
- [x] **Тесты добавлены / обновлены** — `n/a`: нужный end-to-end тест уже существует в `tests/services/test_memory.py` (реальный sqlite-vec, одноразовые эмбеддинги размерности 4, инсерты с разными `user_id`, проверка сортировки по `distance` и фильтрации чужих). Дополнительный round-trip через `Archiver` — в `tests/test_session_archive_roundtrip.py`.
- [x] `git status` чист.

## 6. Этап 3. Журнал диалога и автоматическое восстановление

Закрываем главный пробел: при рестарте теряется `_session_log`. Решение — append-only таблица `dialog_journal` в той же `memory.db` и фоновая задача на старте, которая архивирует «зависшие» сессии.

### Задача 3.1. Схема `dialog_journal` и API

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.1.
- **Связанные документы:** `_docs/memory.md` (новый §4 «Журнал диалога»).
- **Затрагиваемые файлы:** `app/services/dialog_journal.py` (новый), `app/services/memory.py` (init шаринг соединения), `_docs/memory.md`.

#### Описание

Создать сервис `DialogJournal` с API:

- `init()` — создать таблицу `dialog_journal(id, user_id, chat_id, conversation_id, role, kind, content, file_id, file_path, created_at, archived_at)` и индексы по `(user_id, conversation_id, archived_at)`. Поле `kind ∈ {text, document, voice, image, system}`. `archived_at IS NULL` = «не заархивировано».
- `append(user_id, chat_id, conversation_id, role, kind, content, *, file_id=None, file_path=None)` — append-only.
- `pending_conversations() -> list[(user_id, chat_id, conversation_id)]` — все сессии, где есть строки с `archived_at IS NULL`.
- `read_conversation(user_id, conversation_id) -> list[entry]` — для архивации.
- `mark_archived(user_id, conversation_id)` — проставляет `archived_at = now` всем строкам сессии.

API синхронный по сути, оборачиваем в `asyncio.to_thread` (как `SemanticMemory`).

#### Definition of Done

- [x] Файл `app/services/dialog_journal.py` создан, schema идемпотентна (`CREATE IF NOT EXISTS`).
- [x] Unit-тесты на `tmp_path` БД: append → pending → read → mark_archived (6 кейсов).
- [x] `_docs/memory.md` §4 — описание журнала, его места в архитектуре, инвариантов.
- [x] `pytest -q` зелёный, `flake8` зелёный.
- [x] `git status` чист.

### Задача 3.2. Запись текстовых сообщений в журнал

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1.
- **Связанные документы:** `_docs/memory.md` §4, `_docs/architecture.md` §3.6 (события).
- **Затрагиваемые файлы:** `app/services/conversation_subscriber.py`, `app/main.py`, `tests/services/test_conversation_subscriber*` (или новый).

#### Описание

Подписчик на `MessageReceived` и `ResponseGenerated` пишет строку в `dialog_journal` (kind=`text`). Использовать тот же `EventBus`, что и существующие подписчики `on_message_received`/`on_response_generated`.

#### Definition of Done

- [ ] При публикации `MessageReceived`/`ResponseGenerated` в журнал попадает строка с правильным `role`/`kind`.
- [ ] Unit-тест для подписчика.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] **Документация обновлена** — `_docs/memory.md` §4 (поток данных).
- [ ] `git status` чист.

### Задача 3.3. Запись файлов/фото/voice в журнал

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.2.
- **Связанные документы:** `_docs/memory.md` §2.6, §4.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py` (точки `save_file_context`), тесты Telegram-хендлеров.

#### Описание

В трёх точках, где сейчас вызывается `conversations.save_file_context(...)` (document/voice/image), параллельно писать запись в `dialog_journal` (`kind` соответствует типу, `content` — `goal`/transcript-summary, `file_id` и `file_path` — как есть). Не дублировать запись бинарного содержимого: для voice/image сохраняем только метаданные и transcript/описание.

#### Definition of Done

- [ ] Документ/голос/фото попадают в журнал с правильным `kind`, `file_path`, `content`.
- [ ] Unit-тесты Telegram-хендлеров расширены (или добавлены) на проверку записи в журнал.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] `git status` чист.

### Задача 3.4. Фоновая архивация на старте

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 3.2, Задача 3.3.
- **Связанные документы:** `_docs/memory.md` §3.3, §4; `_docs/architecture.md` §3.1.
- **Затрагиваемые файлы:** `app/services/session_bootstrap.py` (расширить) или новый `app/services/journal_recovery.py`, `app/main.py`.

#### Описание

После `_build_components` и до `_start_polling` запускать фоновую корутину `recover_pending_journals(...)`. Алгоритм:

1. Получить список «висящих» сессий через `journal.pending_conversations()`.
2. Для каждой — собрать `read_conversation(...)`, преобразовать в формат `history` (как `_session_log`), вызвать `Archiver.archive(history, conversation_id=..., user_id=..., chat_id=..., progress_callback=None, channel="recovery")`.
3. При успехе — `journal.mark_archived(...)`.
4. Ошибки — логировать, не падать (одна сломанная сессия не блокирует остальные и не валит бот).
5. Параллелизм — последовательная обработка сессий (LLM-нагрузка). Семафор не нужен.

Точка вызова — `asyncio.create_task(...)` в `main()` после `_build_components`, чтобы не блокировать polling.

#### Definition of Done

- [ ] При старте бот стартует polling сразу, восстановление идёт фоном.
- [ ] Unit-тест на `recover_pending_journals` (мок `Archiver`): зависшие сессии помечаются archived; ошибка в одной не валит остальные.
- [ ] Smoke-сценарий вручную: «отправил сообщение → kill -9 процесса → старт → запись попала в `memory_chunks`», результат описан в `_docs/memory.md` §4.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] **Документация обновлена** — `_docs/memory.md` §4 (поток восстановления), `_docs/architecture.md` §3.1 (упоминание задачи в lifecycle).
- [ ] `git status` чист.

### Задача 3.5. Покрыть все случаи начала новой сессии

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.4.
- **Связанные документы:** `_docs/commands.md` § `/new`, § `/reset`, § `/start`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/commands.py`, тесты.

#### Описание

Проверить и закрыть все триггеры начала новой сессии: `/new`, `/reset`, первое сообщение нового пользователя, ротация `conversation_id` по любым иным причинам. Гарантия: до того, как очищается `_session_log`/ротается `conversation_id`, существующая запись в `dialog_journal` либо помечена как заархивированная (если только что прошёл `Archiver`), либо остаётся открытой и будет дозаархивирована при следующем старте/в фоне (на этом спринте — при следующем старте).

Описать инвариант в `_docs/memory.md` §4: «строки в `dialog_journal` с `archived_at IS NULL` — это незавершённый долг».

#### Definition of Done

- [ ] Тесты на `/new`, `/reset`: запись в журнал создана, после успешного `/new` помечена archived.
- [ ] Описание триггеров в `_docs/memory.md` §4.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] `git status` чист.

## 7. Этап 4. Структурное логирование и trace_id

Превращаем плоские строковые логи в JSON, протягиваем `trace_id` через все слои.

### Задача 4.1. JSON-форматтер и `trace_id` через `contextvars`

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** —
- **Связанные документы:** `_docs/stack.md` §8 (логирование), `_docs/architecture.md` §3.3.
- **Затрагиваемые файлы:** `app/logging_config.py`, `app/utils/tracing.py` (новый), `requirements.txt`.

#### Описание

1. Подключить `python-json-logger` (или ручной `logging.Formatter` с `json.dumps`).
2. В `_FORMAT` добавить поля: `timestamp`, `level`, `service` (`ai-multi-agent-system`), `name`, `message`, `trace_id`, `user_id` (если есть), `extra` (произвольный контекст).
3. Создать `app/utils/tracing.py` с `ContextVar trace_id_var`, `new_trace_id()`, `bind_trace_id(value)`, `get_trace_id()`. Поле автоматически попадает в каждую запись через `logging.Filter`.
4. `RotatingFileHandler` остаётся как есть; консольный handler — тоже JSON (для единообразия).

#### Definition of Done

- [ ] Все логи в `data/bot.log` — валидный JSON (можно проверить `jq -c . < bot.log | head`).
- [ ] Каждая запись содержит `trace_id` (или `null`, если контекст не установлен).
- [ ] Unit-тесты на форматтер (что `trace_id` попадает в JSON) и на `tracing.py` (set/get).
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] **Документация обновлена** — `_docs/stack.md` §8 + новый `_docs/observability.md` (или раздел в `architecture.md`).
- [ ] `git status` чист.

### Задача 4.2. Протяжка `trace_id` через middleware и обработчики

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 4.1.
- **Связанные документы:** `_docs/observability.md`.
- **Затрагиваемые файлы:** `app/middlewares/logging_mw.py`, `app/adapters/telegram/handlers/*`, `app/console_main.py`.

#### Описание

Middleware `LoggingMiddleware` на каждое входящее `Update` генерирует свежий `trace_id` (`new_trace_id()`), биндит в contextvar, биндит `user_id` в логи, после выхода — сбрасывает. Аналогично — для консольного адаптера на каждую введённую команду.

#### Definition of Done

- [ ] В логах для одной обработки сообщения — единый `trace_id` от `update_received` до `response_sent`.
- [ ] Тест на middleware (мок Bot, мок handler) проверяет наличие `trace_id` в записях.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] **Документация обновлена** — `_docs/observability.md`.
- [ ] `git status` чист.

### Задача 4.3. Логи в ключевых местах + маскирование секретов

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 4.2.
- **Связанные документы:** `_docs/observability.md`, `_docs/security.md`.
- **Затрагиваемые файлы:** `app/services/llm.py`, `app/services/transcribe.py`, `app/services/vision.py`, `app/services/ocr.py`, `app/tools/http_request.py`, `app/tools/web_search.py`.

#### Описание

В каждой точке, где идёт вызов внешнего сервиса, добавить `logger.info("external.call service=... endpoint=... ...", extra={"trace_id": ...})` и `logger.info("external.ok ... duration_ms=...")` / `logger.error("external.fail ... error=...")`. Аналогично — границы бизнес-действий: «начало архивации», «успех архивации», «начало tool-call», «успех/ошибка tool-call» (часть уже есть — гармонизировать формат).

Маскирование: токены, API-ключи, заголовки `Authorization` — никогда в логах. Реализовать через хелпер `mask_secrets(d: dict) -> dict`.

#### Definition of Done

- [ ] Маскирование секретов покрыто unit-тестом (заголовок `Authorization`, поля `*_token`, `*_key`).
- [ ] В логах при вызовах LLM/transcribe/vision/ocr/http видны входы/выходы по структуре, без сырого payload.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] **Документация обновлена** — `_docs/observability.md`.
- [ ] `git status` чист.

## 8. Этап 5. Error tracking через GlitchTip

Подключаем self-hosted GlitchTip (Sentry-совместимый OSS), чтобы не зависеть от заблокированного `sentry.io`. Конфигурация — через `.env`, по умолчанию выключено (нет DSN — нет инициализации).

### Задача 5.1. Интеграция `sentry-sdk` (off-by-default)

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 4.1.
- **Связанные документы:** `_docs/observability.md`.
- **Затрагиваемые файлы:** `app/observability/__init__.py` (новый), `app/main.py`, `app/console_main.py`, `app/config.py`, `.env.example`, `requirements.txt`.

#### Описание

1. Добавить `sentry-sdk` в `requirements.txt`.
2. Settings: `sentry_dsn: str | None`, `sentry_environment: str = "dev"`, `sentry_traces_sample_rate: float = 0.0` (по умолчанию без performance — только ошибки).
3. `app/observability/__init__.py::setup_sentry(settings)` — инициализирует `sentry_sdk.init(...)` только если `dsn` задан. Включить интеграции `logging`, `asyncio`, `httpx`. PII не отправляем.
4. Хук `before_send`: добавляет `trace_id` и `user_id` из contextvars в `extra`/`tags`.
5. В `main.py` и `console_main.py` — вызов `setup_sentry(settings)` сразу после `setup_logging`.

#### Definition of Done

- [ ] При пустом `SENTRY_DSN` — никаких сетевых запросов, бот стартует как раньше.
- [ ] Unit-тест на `before_send` (что `trace_id` и `user_id` попадают в event).
- [ ] `.env.example` обновлён.
- [ ] `pytest -q`, `flake8` зелёные.
- [ ] **Документация обновлена** — `_docs/observability.md` § Sentry/GlitchTip.
- [ ] `git status` чист.

### Задача 5.2. `docker-compose.yml` для GlitchTip

- **Статус:** ToDo
- **Приоритет:** low
- **Объём:** S
- **Зависит от:** Задача 5.1.
- **Связанные документы:** `_docs/observability.md`.
- **Затрагиваемые файлы:** `docker-compose.observability.yml` (новый), `_docs/observability.md`.

#### Описание

Минимальный `docker-compose.observability.yml` для self-host GlitchTip (web + worker + postgres + redis), по официальной инструкции GlitchTip. В `_docs/observability.md` — пошаговая инструкция: запустить compose, создать организацию, получить DSN, прописать в `.env`. Сам `docker-compose` бота в этом спринте не делаем.

#### Definition of Done

- [ ] `docker compose -f docker-compose.observability.yml up -d` поднимает GlitchTip локально (проверено вручную).
- [ ] Инструкция в `_docs/observability.md` пошаговая, без отсылок к внешним статьям без необходимости.
- [ ] **Документация обновлена** — да.
- [ ] **Тесты добавлены / обновлены** — `n/a` (инфраструктура).
- [ ] `git status` чист.

### Задача 5.3. Smoke на четыре класса искусственных ошибок

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 5.1.
- **Связанные документы:** `_docs/observability.md`.
- **Затрагиваемые файлы:** `tests/observability/test_error_capture.py` (новый).

#### Описание

Один тест с моком `sentry_sdk.transport`. Проверяем, что для четырёх сценариев событие попадает в transport, в нём есть `trace_id` и stack trace:

1. Ручное `raise ValueError(...)` в обработчике.
2. Ошибка в `asyncio.create_task` (асинхронная).
3. Ошибка внешнего вызова (httpx-таймаут — мок).
4. Ошибка данных (`json.JSONDecodeError` на невалидном входе).

#### Definition of Done

- [ ] `pytest tests/observability -q` зелёный, четыре кейса покрыты.
- [ ] `flake8` зелёный.
- [ ] **Документация обновлена** — `_docs/observability.md` § «Проверка через ошибки».
- [ ] `git status` чист.

## 9. Этап 6. CI на GitHub Actions

Финальный шаг — автоматический прогон `pytest` и `flake8` на push/PR.

### Задача 6.1. Workflow `.github/workflows/test.yml`

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.3.
- **Связанные документы:** `_docs/instructions.md` §8.2, §8.3; `_docs/roadmap.md` § «Этап 11».
- **Затрагиваемые файлы:** `.github/workflows/test.yml` (новый).

#### Описание

`actions/checkout@v4` → `actions/setup-python@v5` (Python 3.11) → `pip install -r requirements.txt` → `flake8 app tests` → `pytest -q`. Триггеры — `push` в любую ветку и `pull_request` в `main`. Без матрицы версий, без секретов, без сети к Ollama (тесты должны быть полностью замоканы — проверить, см. этап 2.3).

#### Definition of Done

- [ ] Workflow запускается на push в ветку спринта и проходит зелёным.
- [ ] Тесты не требуют запущенной Ollama / Telegram API.
- [ ] `git status` чист.

### Задача 6.2. Бейдж в `README.md` и описание в документации

- **Статус:** ToDo
- **Приоритет:** low
- **Объём:** XS
- **Зависит от:** Задача 6.1.
- **Связанные документы:** `_docs/instructions.md` §8.
- **Затрагиваемые файлы:** `README.md`, `_docs/instructions.md`.

#### Описание

Добавить бейдж GitHub Actions в шапку `README.md`. В `_docs/instructions.md` §8 — короткое описание CI и того, что push в ветку спринта требует зелёного workflow.

#### Definition of Done

- [ ] Бейдж в `README.md` ведёт на правильный workflow.
- [ ] Описание в `_docs/instructions.md` §8 актуально.
- [ ] `git status` чист.

## 10. Этап 7. Финальная синхронизация документации

### Задача 7.1. Обновить `roadmap.md`, `current-state.md`, `plan.md`

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Все предыдущие задачи.
- **Связанные документы:** `_docs/roadmap.md`, `_docs/current-state.md`, `_board/plan.md`.
- **Затрагиваемые файлы:** `_docs/roadmap.md`, `_docs/current-state.md`, `_board/plan.md`.

#### Описание

После закрытия всех задач спринта:

1. Из `_docs/roadmap.md` удалить «Этап 11. CI» и «Этап 17. Очистка существующего техдолга flake8».
2. В `_docs/current-state.md` §1 добавить факт: «есть `dialog_journal` и автоматическое восстановление», «есть структурное JSON-логирование с trace_id», «есть GlitchTip-интеграция».
3. В `_board/plan.md` — перевод спринта 06 в `Closed`, актуализация сводной таблицы (делаем при формальном закрытии — по запросу пользователя).

#### Definition of Done

- [ ] Roadmap не содержит закрытых здесь этапов.
- [ ] `current-state.md` отражает новое состояние.
- [ ] `git status` чист.

## 11. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | Восстановление при старте делает много медленных вызовов LLM, polling стартует, но первое сообщение пользователя обрабатывается с задержкой. | Запускаем восстановление в `asyncio.create_task` параллельно с `_start_polling`; ошибки изолированы per-conversation. |
| 2 | `dialog_journal` разрастается без TTL. | В этом спринте — вне scope; запись в `_docs/current-state.md` §2 как кандидат на следующий спринт «cleanup TTL». |
| 3 | GlitchTip self-host тяжёл для слабого окружения (postgres+redis+web+worker). | Compose опциональный, бот работает без него; DSN пустой = выключено. |
| 4 | Маскирование секретов неполное → утечка токена в логи. | Тест на маскирование + ручной `git grep` после миграции логов. |
| 5 | CI ловит флэйки тестов, которые сейчас не видны локально. | Если падают — чиним точечно отдельной задачей в этом же спринте, не скрываем `pytest -k`. |

## 12. Сводная таблица задач спринта

| #   | Задача                                                | Приоритет | Объём | Статус | Зависит от |
|-----|-------------------------------------------------------|:---------:|:-----:|:------:|:----------:|
| 1.1 | Закрыть нарушения flake8 в `app/`                     | medium    | S     | Done   | —          |
| 1.2 | Закрыть нарушения flake8 в `tests/`                   | medium    | S     | Done   | —          |
| 1.3 | Пересмотреть `per-file-ignores` в `.flake8`           | low       | XS    | Done   | 1.1, 1.2   |
| 2.1 | Аудит `data/memory.db`                                | high      | S     | Done   | —          |
| 2.2 | Аудит `data/file_contexts.db`                         | medium    | XS    | Done   | —          |
| 2.3 | Сквозной тест RAG-поиска                              | medium    | S     | Done   | 2.1        |
| 3.1 | Схема `dialog_journal` и API                          | high      | M     | Done   | 2.1        |
| 3.2 | Запись текстовых сообщений в журнал                   | high      | S     | ToDo   | 3.1        |
| 3.3 | Запись файлов/фото/voice в журнал                     | high      | S     | ToDo   | 3.2        |
| 3.4 | Фоновая архивация на старте                           | high      | M     | ToDo   | 3.2, 3.3   |
| 3.5 | Покрыть все случаи начала новой сессии                | high      | S     | ToDo   | 3.4        |
| 4.1 | JSON-форматтер и `trace_id` через `contextvars`       | high      | M     | ToDo   | —          |
| 4.2 | Протяжка `trace_id` через middleware                  | high      | S     | ToDo   | 4.1        |
| 4.3 | Логи в ключевых местах + маскирование секретов        | medium    | S     | ToDo   | 4.2        |
| 5.1 | Интеграция `sentry-sdk` (off-by-default)              | medium    | S     | ToDo   | 4.1        |
| 5.2 | `docker-compose.yml` для GlitchTip                    | low       | S     | ToDo   | 5.1        |
| 5.3 | Smoke на четыре класса искусственных ошибок           | medium    | S     | ToDo   | 5.1        |
| 6.1 | Workflow `.github/workflows/test.yml`                 | high      | S     | ToDo   | 1.3        |
| 6.2 | Бейдж в `README.md` и описание в документации         | low       | XS    | ToDo   | 6.1        |
| 7.1 | Обновить `roadmap.md`, `current-state.md`, `plan.md`  | medium    | XS    | ToDo   | все        |

## 13. История изменений спринта

- **2026-05-10** — спринт открыт, ветка `feature/06-reliability-and-observability` создана от `main`.
- **2026-05-10** — закрыта задача 1.1: flake8 в `app/` базовый проход чист (58 нарушений → 0).
- **2026-05-10** — закрыта задача 1.2: flake8 в `tests/` чист (40 нарушений → 0).
- **2026-05-10** — закрыта задача 1.3: удалён больше ненужный `per-file-ignores: tests/*:E501` из `.flake8`. Этап 1 завершён.
- **2026-05-10** — закрыта задача 2.1: аудит схемы `data/memory.db`, вердикт по полям зафиксирован в `_docs/memory.md` §3.5.1 (`chat_id` остаётся как future-proof для Web/MAX-адаптеров).
- **2026-05-10** — закрыта задача 2.2: аудит `data/file_contexts.db` и синхронизация `_docs/memory.md` §2.6 с кодом (PK = `(user_id, message_id)`, опечатка `files_contexts.db`); мёртвых полей нет.
- **2026-05-10** — закрыта задача 2.3: верифицировано, что сквозной тест RAG (`tests/services/test_memory.py::test_search_orders_by_distance_and_filters_by_user`) уже покрывает insert→search с фильтром `scope_user_id` на реальном sqlite-vec. Этап 2 завершён.
- **2026-05-10** — закрыта задача 3.1: создан сервис `DialogJournal` (`app/services/dialog_journal.py`) с таблицей в `data/memory.db` и API (`init/append/pending_conversations/read_conversation/mark_archived`); покрыт 6 unit-тестами; §4 в `_docs/memory.md` расписан.
