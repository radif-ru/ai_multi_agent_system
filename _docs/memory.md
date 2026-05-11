# Память агента

Документ описывает два слоя памяти и сценарий `/new`. Связанные документы: `architecture.md` §3.5–3.6, `requirements.md` §1.4, `commands.md` § `/new` и § `/reset`.

## 1. Два слоя

| Слой               | Где живёт                          | Что хранит                                      | Когда теряется                          |
|--------------------|------------------------------------|-------------------------------------------------|------------------------------------------|
| **Краткосрочная**  | RAM процесса (`ConversationStore`) | Текущая сессия: `[{role, content}, ...]` per-user | Рестарт процесса; `/reset`; `/new`     |
| **Долгосрочная**   | `sqlite-vec` (`MEMORY_DB_PATH`)    | Саммари прошлых сессий, чанки + эмбеддинги      | Удаление `.db`-файла (вручную)          |

Сырые сообщения **не пишутся** в долгосрочную память (CON-1) — только саммари. Это даёт минимальный приватный след: даже при компрометации `.db` нет переписки в открытом виде.

## 2. Краткосрочная память (in-memory)

Реализация — `app/services/conversation.py::ConversationStore`. Заимствована из `ai_tg_bot` (предыдущий проект автора), уточнённая под мульти-агентный сценарий: добавлено понятие **`conversation_id`** (UUID или короткий слаг), который ротируется на `/new`. Помимо «rolling»-буфера `_messages` (который живёт под лимитом `HISTORY_MAX_MESSAGES` и периодически сжимается `replace_with_summary`), ведётся параллельный **полный лог сессии** `_session_log` — см. §2.5. Также ведётся **контекст файлов** `_file_contexts` для reply на файлы — см. §2.6.

### 2.1 Структура

```python
class ConversationStore:
    # user_id -> list[{role: "user"|"assistant"|"system", content: str}]
    # rolling-буфер для LLM, сжимается replace_with_summary
    _messages: dict[int, list[dict]]
    # user_id -> append-only полный лог текущей сессии (для /new)
    _session_log: dict[int, list[dict]]
    # user_id -> текущий conversation_id (для метаданных архива)
    _conversation_ids: dict[int, str]
    # (user_id, message_id, file_type) -> context текст
    # для reply на файлы (фото, документы, голосовые)
    _file_contexts: dict[tuple[int, int, str], str]
```

### 2.2 API

| Метод | Описание |
|-------|----------|
| `get_history(user_id) -> list[dict]` | Возвращает **копию** списка сообщений. Мутации снаружи не влияют. |
| `add_user_message(user_id, text)` | Дописать сообщение пользователя; FIFO-обрезка по `HISTORY_MAX_MESSAGES`. |
| `add_assistant_message(user_id, text)` | Аналогично для ассистента. |
| `replace_with_summary(user_id, summary, kept_tail=2)` | Заменить всё, кроме последних `kept_tail` сообщений, одним `{"role": "system", "content": "Краткое резюме предыдущей части диалога: ..."}`. Используется при срабатывании in-session порога. |
| `current_conversation_id(user_id) -> str` | Текущий идентификатор сессии. |
| `rotate_conversation_id(user_id) -> str` | Сгенерировать новый id и сохранить. Возвращает старый. |
| `clear(user_id)` | Очистить всё: `_messages`, `_session_log`, `_file_contexts` и `conversation_id`. |
| `get_session_log(user_id) -> list[dict]` | Копия **полного** лога сессии (без in-session compaction). Используется `cmd_new` → `Archiver`. См. §2.5. |
| `save_file_context(user_id, message_id, file_type, context)` | Сохранить контекст файла для reply. Используется при обработке документов, голосовых сообщений и фотографий. |
| `get_file_context(user_id, message_id, file_type) -> str | None` | Получить контекст файла по message_id и типу файла. Используется при reply на файлы. |

### 2.3 In-session суммаризация (порог)

Триггерится подписчиком на событие `ResponseGenerated` после успешной генерации ответа LLM (см. `events.md`):

```python
# В app/services/summarizer_subscriber.py
async def on_response_generated_summarize(event: ResponseGenerated, ...):
    history = conversations.get_history(user_id)
    if len(history) >= settings.history_summary_threshold:
        summary = await summarizer.summarize(history[:-2], model=...)
        conversations.replace_with_summary(user_id, summary, kept_tail=2)
```

Подписчик регистрируется в `main.py` и `console_main.py` **после** подписчика записи в `ConversationStore`, чтобы к моменту суммаризации ответ ассистента уже был записан в стор. Падение суммаризации → `WARNING in-session суммаризация не удалась ...`, история остаётся, другие подписчики не страдают. См. `architecture.md` §4 и `events.md`.

### 2.4 Подгрузка истории в LLM

Без подгрузки истории каждый ход выглядит как новая сессия — модель не помнит предыдущих сообщений (см. отчёт пользователя из обратной связи спринта 02). Поэтому `Executor.run` принимает `history` явным параметром и склеивает финальный список сообщений как:

```
[system_prompt] + history + [user: goal]?
```

Порядок и инвариант:

1. Адаптер (Telegram-handler `messages.py`) публикует событие `MessageReceived` **до** `core.handle_user_task` — подписчик события вызывает `ConversationStore.add_user_message(user_id, text)`, то есть текущий запрос уже лежит последним элементом в `history`.
2. `core.handle_user_task` достаёт `history = conversations.get_history(user_id)` и передаёт его в `Executor.run` целиком.
3. `Executor.run` собирает `messages = [system] + history`. Если последний элемент `history` уже совпадает с `{"role": "user", "content": goal}` — дубликат не добавляется; иначе (например, тестовый сценарий без адаптера) `goal` дописывается отдельным `user`-сообщением.
4. Внутрицикловые `assistant`/`Observation`-пары копятся в локальном списке `messages` Executor'а и **не** пишутся в `ConversationStore`. В долгую краткосрочную историю попадает только финальный ответ ассистента — его дописывает подписчик события `ResponseGenerated` после возврата `Executor.run` (вызывает `add_assistant_message`).

```
ConversationStore                       Executor.run
[user: «Привет, я Радиф»]    ─────►    messages = [system,
[assistant: «Привет, Радиф»]                       user: «Привет, я Радиф»,
[user: «Как меня зовут?»]                          assistant: «Привет, Радиф»,
                                                   user: «Как меня зовут?»]
       ▲
       │
       └── подписчик ResponseGenerated вызывает add_assistant_message(«Тебя зовут Радиф») ◄── финальный ответ Executor.run
```

Лимит длины истории защищён существующим `HISTORY_MAX_MESSAGES` (FIFO в `ConversationStore`) и `HISTORY_SUMMARY_THRESHOLD` (in-session суммаризация — см. §2.3).

### 2.5 Полный лог сессии (`_session_log`)

**Проблема**, которую решает этот буфер (обратная связь пользователя, спринт 02): in-session суммаризация (`replace_with_summary`, §2.3) разрушает `_messages` до `summary + last 2`. Если «/new» архивировал бы именно `_messages`, ранние реплики (например, «Привет, я Радиф») в долгосрочную память не попадают и `memory_search` их не находит после `/new`.

**Решение**: параллельно с `_messages` ведётся append-only буфер `_session_log` — все `user`/`assistant` сообщения текущей сессии в исходном виде, без сжатия и без FIFO-усечения по `HISTORY_MAX_MESSAGES`.

Инварианты:

1. `add_user_message(user_id, text)` и `add_assistant_message(user_id, text)` дублируют запись: одновременно в `_messages` (как раньше) и в `_session_log`. Эти методы вызываются подписчиками событий `MessageReceived` и `ResponseGenerated` соответственно.
2. `add_system_message` и `replace_with_summary` — **не трогают** `_session_log`. Это оптимизации контекста для LLM, они не относятся к исходному диалогу.
3. `get_session_log(user_id)` возвращает независимую копию (внешние мутации не влияют на стор).
4. `clear(user_id)` и `rotate_conversation_id(user_id)` **обнуляют** лог пользователя — новая сессия начинается с пустого лога.
5. Верхняя страховка `Settings.session_log_max_messages` (env `SESSION_LOG_MAX_MESSAGES`, default 1000): при переполнении — отбрасывается голова лога и выдаётся `WARNING`. Это редкий сценарий (аномально длинная сессия без `/new`).

**Инвариант высокого уровня**: in-session compaction оптимизирует только контекст для LLM (`_messages`); долгосрочная память при `/new` всегда видит сессию целиком (`_session_log`).

### 2.6 Контекст файлов

Для поддержки reply на файлы (фото, документы, голосовые) ведётся контекст файлов. Это позволяет агенту понимать, на какой файл пользователь отвечает, даже если файл был загружен ранее в сессии.

**Проблема**: без контекста файлов при reply на документ/голосовое сообщение агент не видит содержимое файла и не может дать осмысленный ответ.

**Решение (с задачи 06.3-bis.2)**: при обработке файлов (`handle_document`/`handle_voice`/`handle_photo`) Telegram-хендлер публикует событие `MessageReceived` с полями `kind`/`file_id`/`file_path`/`message_id`/`text=<goal>`. Подписчик `on_message_received_journal` пишет запись в таблицу `dialog_journal` (`data/memory.db`, см. §4.1) с полем `message_id`. При reply `ConversationStore.get_file_context(user_id, message_id)` тянет `content` из `dialog_journal` (`SELECT content … WHERE user_id=? AND message_id=? ORDER BY id DESC LIMIT 1`) и подмешивает его в текст входящего сообщения. Словарь `_file_contexts` в `ConversationStore` остаётся как in-memory кеш горячих чтений.

Инварианты:

1. Запись контекста файла в БД делает **только** подписчик `on_message_received_journal` (никаких `save_file_context` в хендлерах). Источник истины — `dialog_journal`.
2. `ConversationStore.get_file_context(user_id, message_id)` сначала ищет в кеше `_file_contexts`, затем в `dialog_journal` через `journal_db_path` (передаётся из `app/main.py`/`app/console_main.py`). Если `journal_db_path` не задан — fallback в `None`, контекст не теряется (это путь по умолчанию только в legacy-сценариях).
3. При `/new` (через `clear(user_id)`) сбрасывается только in-memory кеш. Записи журнала живут до `mark_archived(...)`, который вызывает `cmd_new` после успешного `Archiver.archive(...)` (см. §4.3, задача 06.3.5).
4. Файлы на диске (документы, голосовые) не удаляются сразу после обработки — живут до `/new` или TTL cleanup, как и изображения.
5. Изоляция файлов по пользователям: файлы сохраняются в отдельные каталоги `data/tmp/{user_id}/`.

**Типы файлов** (поле `kind` в `dialog_journal`):
- `image` — изображения (фото)
- `document` — документы (PDF, TXT, MD)
- `voice` — голосовые сообщения

**Использование в handler'ах**:
- `handle_photo`: публикует `MessageReceived(kind="image", file_id, file_path, message_id, text=goal)`.
- `handle_document`: публикует `MessageReceived(kind="document", file_id, file_path, message_id, text=goal)`.
- `handle_voice`: публикует `MessageReceived(kind="voice", file_id, file_path, message_id, text=goal)` после транскрипции.
- `handle_text`: при reply на файл вызывает `get_file_context(user_id, reply_msg_id)` и подмешивает результат.

#### 2.6.1 Унифицированное хранение в `dialog_journal`

С задачи 06.3-bis.2 контекст файла лежит в той же таблице `dialog_journal` (см. §4.1), что и текст диалога: колонка `message_id` хранит ID сообщения Telegram, `kind` — тип файла, `content` — текст `goal`, `file_id`/`file_path` — данные для `FileIdMapper`. Отдельная база `data/file_contexts.db` упразднена и переименована при одноразовой миграции в `data/file_contexts.db.migrated-<ts>` (см. §4.1 и `app/services/file_contexts_migration.py`).

Аудит использования полей в `dialog_journal` для reply-сценария:

| Поле | INSERT | SELECT / использование |
|------|:------:|------------------------|
| `user_id` | да | `WHERE user_id=?` в `get_file_context`, `FileIdMapper`. |
| `message_id` | да (`kind ∈ {document,voice,image}`) | `WHERE message_id=?` в `get_file_context`; индекс `ix_journal_message`. |
| `kind` | да | различает текст и тип файла; пишется подписчиком. |
| `content` | да | `SELECT content` в `get_file_context` — это `goal`-текст. |
| `file_id` | да | `SELECT DISTINCT file_id, file_path` в `FileIdMapper.init`. |
| `file_path` | да | `SELECT file_path` в `FileIdMapper.get_path`. |
| `created_at` | да | для отладки/TTL. |
| `archived_at` | через `mark_archived` | помечает строки сессии как закрытые после `/new` (см. §4.3). |

## 3. Долгосрочная память (sqlite-vec)

### 3.1 Почему `sqlite-vec`

- **Один файл** `.db` на всё (метаданные + векторы) → проще бэкап / удаление / тесты.
- **Без нативной сборки FAISS / без отдельного сервиса** (Chroma и т. п.) → минимум зависимостей, легко мокается в тестах.
- **Pure C extension**, поднимается в обычный `sqlite3` модуль stdlib через `sqlite_vec.load(conn)` — не требует особых runtime-поддержек.
- **Активно развивается** в 2025; преемник `sqlite-vss`, который рекомендован самим автором (asg017).

### 3.2 Embedding-модель

`nomic-embed-text` (768 dimensions) через Ollama. Поднимается так же, как LLM: `ollama pull nomic-embed-text`. Размерность настраивается через `EMBEDDING_DIMENSIONS` — должна совпадать с моделью, иначе `sqlite-vec` упадёт при `INSERT`.

Альтернативы (для пользователя — через `.env`, без правки кода): `mxbai-embed-large` (1024d), `all-minilm` (384d). Достаточно поменять `EMBEDDING_MODEL` + `EMBEDDING_DIMENSIONS`. Старая БД **не совместима** с новой моделью (другая размерность) — придётся удалить `.db` или вынести в другой файл.

### 3.3 Сценарий `/new` (архивирование)

Реализация — `app/services/archiver.py::Archiver`.

На вход `Archiver.archive(history, ...)` подаётся именно **полный лог сессии** (`ConversationStore.get_session_log(user_id)`, см. §2.5), а не in-session `get_history()` — иначе суммаризатор увидит уже усечённую `replace_with_summary` верхушку и ранние факты будут потеряны.

После успешного завершения архивирования `Archiver` публикует событие `ConversationArchived` (см. `events.md`), на которое могут подписываться побочные эффекты (например, очистка временных файлов). При неуспехе архивирования событие не публикуется.

```
история сессии        +- Summarizer.summarize ----------+
[{role,content}, ...] |  (Ollama chat с системным       |  -> резюме (одна строка)
                       +- _prompts/summarizer.md)        |
                                                          |
                       +- chunk(summary,                  |
                       |   size=MEMORY_CHUNK_SIZE,        |  -> [chunk_1, chunk_2, ...]
                       |   overlap=MEMORY_CHUNK_OVERLAP)  |
                                                          |
для каждого чанка:    +- OllamaClient.embed(chunk_i)     |  -> вектор[EMBEDDING_DIMENSIONS]
                       |  (модель EMBEDDING_MODEL)         |
                                                          |
                       +- SemanticMemory.insert(           |
                       |    chunk_i, vector_i,            |  -> запись в sqlite-vec
                       |    metadata={                    |
                       |      conversation_id, chat_id,   |
                       |      user_id, chunk_index,       |
                       |      created_at                  |
                       |    })                            |
                                                          v
                       ConversationStore.clear(user_id) +
                       ConversationStore.rotate_conversation_id(user_id)
```

После архивирования handler `/new` отправляет пользователю:

```
Архивировано N чанков, новая сессия открыта.
```

### 3.4 Поиск по архиву (tool `memory_search`)

Доступен агенту в любой сессии. Контракт — в `tools.md` § `memory_search`. Кратко:

```python
async def run(args: dict, ctx: ToolContext) -> str:
    query = args["query"]
    top_k = args.get("top_k", settings.memory_search_top_k)
    embedding = await ctx.llm.embed(query, model=settings.embedding_model)
    rows = await ctx.semantic_memory.search(embedding, top_k=top_k, scope_user_id=ctx.user_id)
    return _format_search_result(rows)
```

`scope_user_id` — фильтрует поиск по `user_id`, чтобы один пользователь не видел чужие саммари.

### 3.5 Схема БД

Файл — `MEMORY_DB_PATH` (default `data/memory.db`). Содержит обычную таблицу метаданных и `vec0`-виртуальную таблицу для KNN.

```sql
-- метаданные (обычная таблица)
CREATE TABLE IF NOT EXISTS memory_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,  -- rowid, связь с memory_vec
    user_id         INTEGER NOT NULL,                    -- фильтр поиска (scope_user_id)
    chat_id         INTEGER NOT NULL,                    -- future-proof для групп/каналов
    conversation_id TEXT    NOT NULL,                    -- идентификатор сессии (/new)
    chunk_index     INTEGER NOT NULL,                    -- порядковый номер чанка
    created_at      TEXT    NOT NULL,                    -- ISO 8601, для TTL/cleanup
    text            TEXT    NOT NULL                     -- текст чанка
);
CREATE INDEX IF NOT EXISTS ix_memory_user ON memory_chunks(user_id);
CREATE INDEX IF NOT EXISTS ix_memory_conv ON memory_chunks(conversation_id);
CREATE INDEX IF NOT EXISTS ix_memory_created ON memory_chunks(created_at);  -- для cleanup старых записей

-- векторы (sqlite-vec virtual table)
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0 (
    embedding float[768]
);
```

Связь: `memory_chunks.id == memory_vec.rowid` (используем общий rowid).

#### 3.5.1 Аудит использования полей

Аудит проведён в Спринте 06 (задача 2.1). Цель — зафиксировать, какие поля реально работают в текущем коде, какие персистятся «про запас», и принять решение по очистке.

| Поле | INSERT | SELECT | WHERE / ORDER | Индекс | Статус |
|------|:------:|:------:|---------------|--------|--------|
| `id` | auto | да (`JOIN memory_vec`) | — | PK | используется. |
| `user_id` | да | — | `WHERE mc.user_id = ?` | `ix_memory_user` | используется по горячему пути (`scope_user_id`). |
| `chat_id` | да | — | — | — | **future-proof**: персистится, но в WHERE/SELECT не участвует. Решение — **оставить** (см. ниже). |
| `conversation_id` | да | да (в результате `search`) | — | `ix_memory_conv` | возвращается клиенту, индекс пока «спит» (нет WHERE по нему). |
| `chunk_index` | да | — | — | — | персистится, читается только в тестах при ручной верификации; кандидат на удаление в будущем. |
| `created_at` | да | да (в результате `search`) | — | `ix_memory_created` | возвращается клиенту, индекс заготовлен под будущий TTL/cleanup. |
| `text` | да | да | — | — | основной контент. |

Вердикт по `chat_id`: **остаётся**. Удаление потребует пересоздания таблицы (sqlite-DROP COLUMN полноценно появился только в 3.35) и миграции существующих данных без выигрыша по производительности — поле NOT NULL и не блокирует никаких индексов. Использование запланировано в этапах roadmap 5 (Web-адаптер) и 6 (MAX-адаптер), где `chat_id` уже не будет совпадать с `user_id`.

Виртуальная таблица `memory_vec` (`vec0`) и её служебные таблицы (`memory_vec_chunks`, `memory_vec_rowids`, `memory_vec_vector_chunks00`) создаются расширением `sqlite-vec` автоматически и проверены сквозным тестом RAG-поиска (см. задачу 2.3 в `_board/sprints/06-reliability-and-observability.md`).

`INSERT`:

```sql
INSERT INTO memory_chunks (user_id, chat_id, conversation_id, chunk_index, created_at, text)
VALUES (?, ?, ?, ?, ?, ?);
INSERT INTO memory_vec (rowid, embedding) VALUES (last_insert_rowid(), ?);
```

KNN-`SELECT`:

```sql
SELECT mc.id, mc.text, mc.conversation_id, mc.created_at, v.distance
FROM memory_vec AS v
JOIN memory_chunks AS mc ON mc.id = v.rowid
WHERE v.embedding MATCH ?
  AND mc.user_id = ?
ORDER BY v.distance
LIMIT ?;
```

### 3.6 Авто-подгрузка архива в новую сессию

Без подгрузки архива пользователь после `/new` получает «амнезию»: модель про прошлые сессии не знает, пока сама не догадается вызвать `memory_search`. На практике она этого почти не делает (`qwen3.5:4b`, короткие запросы). Чтобы это починить, `core.handle_user_task` при первом сообщении новой сессии (`len(history) == 1`) автоматически тянет релевантный контекст из `SemanticMemory` и подмешивает его как `system`-сообщение.

Алгоритм:

1. `core.handle_user_task` обнаруживает, что после публикации события `MessageReceived` (подписчик которого вызывает `add_user_message`) история содержит ровно один элемент (новая или сброшенная сессия).
2. Если `Settings.session_bootstrap_enabled` и `SemanticMemory` доступна — вызывает `OllamaClient.embed(text, model=embedding_model)`.
3. `SemanticMemory.search(embedding, top_k=Settings.session_bootstrap_top_k, scope_user_id=user_id)` возвращает релевантные чанки.
4. Если найденных чанков нет — авто-подгрузка пропускается (пустой архив, новый пользователь).
5. Иначе чанки склеиваются в один `system`-message формата:
   ```
   Контекст из прошлых сессий пользователя (используй только если он
   действительно относится к текущему запросу):

   - <chunk_1>
   - <chunk_2>
   - ...
   ```
   и **подмешивается в начало `history`** (т. е. до `user`-сообщения с `goal`).
6. `Executor.run` строит `messages = [main_system, bootstrap_system, user: goal]`. Никакой записи в `ConversationStore` авто-подгрузка не делает — это «одноразовая» подмесь только для текущего LLM-вызова.

Падение `OllamaClient.embed` или `SemanticMemory.search` → `WARNING session_bootstrap failed ...`, основной ход не страдает: сессия стартует без авто-контекста (как в Спринте 01). То же поведение при `Settings.session_bootstrap_enabled = false` или `SemanticMemory is None`.

Параметры (`_docs/stack.md` §9):

- `SESSION_BOOTSTRAP_ENABLED` (bool, default `true`) — выключатель.
- `SESSION_BOOTSTRAP_TOP_K` (int, default `3`) — сколько чанков подмешивать.

Точка реализации — `app/services/session_bootstrap.py` (отдельный модуль), вызывается из `core.handle_user_task`. Tool `memory_search` остаётся доступен агенту: авто-подгрузка не отменяет ручной поиск, а покрывает типовой кейс «первый ход после `/new`».

## 4. Журнал диалога (`dialog_journal`)

Сейчас рабочая копия диалога живёт только в RAM `ConversationStore._session_log` (см. §2.5). При **краше**, **рестарте процесса** или **прерывании пользователем** до вызова `/new` сессия теряется до того, как успеет попасть в `memory_chunks`.

Решение — параллельный append-only журнал в той же `data/memory.db`, в который пишется каждое сообщение сессии (текст пользователя, ответ агента, метаданные файлов/голосовых/фото). При следующем старте бота фоновая задача находит «зависшие» сессии (`archived_at IS NULL`) и архивирует их через тот же `Archiver`, что и `/new`.

Реализация — `app/services/dialog_journal.py::DialogJournal`. Соединение отдельное от `SemanticMemory` (журналу не нужно расширение `sqlite-vec`).

### 4.1 Схема

```sql
CREATE TABLE IF NOT EXISTS dialog_journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    chat_id         INTEGER NOT NULL,
    conversation_id TEXT    NOT NULL,
    role            TEXT    NOT NULL,    -- "user" | "assistant" | "system"
    kind            TEXT    NOT NULL,    -- "text" | "document" | "voice" | "image" | "system"
    content         TEXT    NOT NULL,    -- для файлов — goal/transcript/описание; сырой бинарь не пишется
    file_id         TEXT,                -- для kind ∈ {document, voice, image} — id из FileIdMapper
    file_path       TEXT,                -- абсолютный путь во временной директории
    created_at      TEXT    NOT NULL,    -- ISO 8601
    archived_at     TEXT,                 -- NULL = долг; ISO 8601 = сессия уже в memory_chunks
    message_id      INTEGER               -- id входящего сообщения адаптера (Telegram message_id);
                                          -- NULL для ответов ассистента и записей без привязки
);
CREATE INDEX IF NOT EXISTS ix_journal_pending  ON dialog_journal(user_id, conversation_id, archived_at);
CREATE INDEX IF NOT EXISTS ix_journal_created  ON dialog_journal(created_at);
CREATE INDEX IF NOT EXISTS ix_journal_message  ON dialog_journal(user_id, message_id)
    WHERE message_id IS NOT NULL;
```

Колонка `message_id` добавлена в задаче 06.3-bis.1: она нужна, чтобы свести воедино журнал и старую таблицу `file_contexts` (PK там был `(user_id, message_id)`) — после этапа 3-bis `ConversationStore.get_file_context` и `FileIdMapper` читают из `dialog_journal` по этому же ключу, а `data/file_contexts.db` мигрируется один раз и удаляется. Миграция реализована в `app/services/file_contexts_migration.py::migrate_file_contexts_to_journal(...)`: при старте процесса (см. `app/main.py`/`app/console_main.py`) она читает старую таблицу, добавляет строки в `dialog_journal` с `conversation_id = "legacy"`, `archived_at = now()` (эти строки уже «закрыты» и не подбираются фоновой архивацией) и переименовывает источник в `data/file_contexts.db.migrated-<ts>`.

### 4.2 API

| Метод | Описание |
|-------|----------|
| `init()` | Создать таблицу и индексы (идемпотентно). |
| `append(user_id, chat_id, conversation_id, role, kind, content, file_id=None, file_path=None, message_id=None)` | Append-only запись одной строки. Валидирует `role` и `kind`. `message_id` (опционально) — id входящего сообщения адаптера. |
| `pending_conversations() -> list[(user_id, chat_id, conversation_id)]` | Все сессии, в которых есть хотя бы одна строка с `archived_at IS NULL`. Упорядочены по `MIN(created_at)`. |
| `read_conversation(user_id, conversation_id) -> list[dict]` | Все строки одной сессии в хронологическом порядке. |
| `mark_archived(user_id, conversation_id) -> int` | Проставить `archived_at = now()` всем строкам сессии с `archived_at IS NULL`. Возвращает количество затронутых строк. |

### 4.3 Инвариант и триггеры начала новой сессии

Строка с `archived_at IS NULL` — это **незавершённый долг**: либо сессия активна, либо процесс рестартовал до архивации. Долг гасится одним из путей:

1. **Команда `/new`** — `Archiver.archive(...)` отрабатывает синхронно в обработчике, после успеха `journal.mark_archived(user_id, conversation_id)` закрывает строки сессии в журнале (`app/commands/registry.py::cmd_new`). Только после этого `ConversationStore.clear(...)` и `rotate_conversation_id(...)` начинают новую сессию. Если `Archiver` упал — `mark_archived` не вызывается, история не очищается, `conversation_id` не ротируется; журнал остаётся открытым долгом до следующего успешного `/new` или фоновой архивации.
2. **Фоновая задача** `recover_pending_journals(...)` при старте процесса (см. §4.4) — обходит `pending_conversations()` и поднимает их через тот же `Archiver`. На успехе — `mark_archived(...)`.
3. **Команда `/reset`** — `ConversationStore.clear(...)` + `rotate_conversation_id(...)` без вызова `Archiver`. Журнал **не помечается** `archived_at`: сессия остаётся открытым долгом и будет дозаархивирована фоновой задачей при следующем старте процесса. Так мы не теряем диалог даже если пользователь нажал `/reset` по ошибке.
4. **Первое сообщение нового пользователя / ротация `conversation_id` по другим причинам.** На сегодня в коде нет автоматической ротации `conversation_id` без явной пользовательской команды (`/new` / `/reset`): для нового пользователя `ConversationStore.current_conversation_id(...)` лениво создаёт новый идентификатор при первом обращении, а старые сессии (если они есть в журнале) подбираются фоновой задачей независимо от того, какой `conversation_id` сейчас активен.

Сырой бинарь файлов в журнал не попадает — только метаданные (`file_id`, `file_path`, transcript для voice, описание/OCR для image, goal для document). Это согласовано с CON-1 «приватный след должен быть минимальным».

### 4.4 Фоновое восстановление при старте

Реализация — `app/services/journal_recovery.py::recover_pending_journals(journal, archiver)`. Корутина запускается из `app/main.py::main` через `asyncio.create_task` сразу после `_build_components` и параллельно с `_start_polling`, чтобы не задерживать старт polling. Алгоритм:

1. `journal.pending_conversations()` → список «висящих» сессий `(user_id, chat_id, conversation_id)`, упорядоченный по времени появления.
2. Для каждой сессии — `journal.read_conversation(...)` и преобразование строк в формат `[{role, content}, ...]` (file-метаданные уже зашиты в `content`, см. §4.1; пустые `content` отфильтровываются).
3. Если после фильтрации история пуста — сессия закрывается напрямую `journal.mark_archived(...)` без вызова `Archiver` (нечего суммаризировать).
4. Иначе — `Archiver.archive(history, conversation_id=..., user_id=..., chat_id=..., user=None, channel="recovery")` (тот же путь, что и `/new`; событие `ConversationArchived` не публикуется, потому что `user is None`).
5. На успехе — `journal.mark_archived(user_id, conversation_id)`. На ошибке — лог, `summary["failed"] += 1`, переход к следующей сессии. Одна сломанная сессия не валит остальные и не валит бот.

Сессии обрабатываются последовательно (LLM-нагрузка), без `asyncio.gather` и семафоров. При завершении процесса до окончания восстановления — `recovery_task.cancel()` в `finally` блока `main()`; следующий старт подберёт оставшиеся сессии тем же путём.

**Smoke-сценарий «kill -9 → старт»** (ожидаемое поведение): отправили текст пользователю → подписчик `on_message_received_journal` записал строку в `dialog_journal` (`archived_at IS NULL`); процесс прервали (`kill -9`, краш, рестарт хоста); следующий старт через `python -m app` → `recover_pending_journals` поднимает сессию через `Archiver` → строка получает `archived_at`, чанк попадает в `memory_chunks` и виден в `MemorySearchTool`. Unit-тесты на алгоритм — `tests/services/test_journal_recovery.py`.

## 5. Что НЕ хранится (по дизайну)

- **Сырые сообщения диалога в `memory_chunks`** — туда идут только саммари при `/new` или фоновом восстановлении (CON-1). Полный диалог временно хранится в `dialog_journal` до архивации.
- **Системные промпты** — они в `_prompts/`, не в БД.
- **Вызовы tools и observations** — они в логах, не в архивной памяти.
- **Учётные записи Telegram / профили пользователей** — для MVP не нужны (`user_id` Telegram достаточно как ключ).

## 6. Что **может** появиться в архиве в будущем (НЕ MVP)

(см. `roadmap.md`)

- **Per-skill memory** — отдельная пространственная коллекция чанков для каждого скилла.
- **Per-task memory** — пишем в архив краткое резюме каждой выполненной задачи, чтобы Critic мог сравнивать.
- **TTL и очистка**: автоматическое удаление чанков старше N дней.
- **Поиск с metadata-фильтрами** (по дате, conversation_id и т. п.) через `WHERE` в SQL — `sqlite-vec` это поддерживает, но контракт tool `memory_search` пока не использует.

## 7. Тестируемые свойства

(Чек-лист для `tests/services/test_memory.py` и `tests/services/test_archiver.py` в Спринте 01.)

- `SemanticMemory.init()` создаёт обе таблицы; повторный вызов идемпотентен.
- `SemanticMemory.insert(...)` пишет одну строку в `memory_chunks` и одну запись в `memory_vec`; rowid'ы совпадают.
- `SemanticMemory.search(embedding, top_k=K)` возвращает up-to-K строк, отсортированных по `distance`.
- Поиск ограничен по `user_id` — чужие чанки не возвращаются.
- `Archiver.archive(...)` корректно режет резюме на чанки нужного размера, считает `chunk_index` от 0.
- Падение `Summarizer.summarize` → `Archiver` бросает понятную ошибку, **не** очищает `ConversationStore`.
- Падение `OllamaClient.embed` на одном из чанков → транзакция откатывается, в `memory_chunks` нет «осиротевших» строк.

Тесты используют `tmp_path` для `.db`-файла; `OllamaClient` мокается, `sqlite-vec` грузится по-настоящему (это часть проверки, что окружение работает).
