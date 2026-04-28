# Память агента

Документ описывает два слоя памяти и сценарий `/new`. Связанные документы: `architecture.md` §3.5–3.6, `requirements.md` §1.4, `commands.md` § `/new` и § `/reset`.

## 1. Два слоя

| Слой               | Где живёт                          | Что хранит                                      | Когда теряется                          |
|--------------------|------------------------------------|-------------------------------------------------|------------------------------------------|
| **Краткосрочная**  | RAM процесса (`ConversationStore`) | Текущая сессия: `[{role, content}, ...]` per-user | Рестарт процесса; `/reset`; `/new`     |
| **Долгосрочная**   | `sqlite-vec` (`MEMORY_DB_PATH`)    | Саммари прошлых сессий, чанки + эмбеддинги      | Удаление `.db`-файла (вручную)          |

Сырые сообщения **не пишутся** в долгосрочную память (CON-1) — только саммари. Это даёт минимальный приватный след: даже при компрометации `.db` нет переписки в открытом виде.

## 2. Краткосрочная память (in-memory)

Реализация — `app/services/conversation.py::ConversationStore`. Заимствована из `ai_tg_bot` (предыдущий проект автора), уточнённая под мульти-агентный сценарий: добавлено понятие **`conversation_id`** (UUID или короткий слаг), который ротируется на `/new`. Помимо «rolling»-буфера `_messages` (который живёт под лимитом `HISTORY_MAX_MESSAGES` и периодически сжимается `replace_with_summary`), ведётся параллельный **полный лог сессии** `_session_log` — см. §2.5.

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
| `clear(user_id)` | Очистить всё: `_messages`, `_session_log` и `conversation_id`. |
| `get_session_log(user_id) -> list[dict]` | Копия **полного** лога сессии (без in-session compaction). Используется `cmd_new` → `Archiver`. См. §2.5. |

### 2.3 In-session суммаризация (порог)

Срабатывает в обработчике сообщения после ответа LLM:

```python
if len(store.get_history(user_id)) >= settings.history_summary_threshold:
    summary = await summarizer.summarize(history[:-2], model=...)
    store.replace_with_summary(user_id, summary, kept_tail=2)
```

Падение суммаризации → `WARNING summarize failed ...`, история остаётся. См. `architecture.md` §4.

### 2.4 Подгрузка истории в LLM

Без подгрузки истории каждый ход выглядит как новая сессия — модель не помнит предыдущих сообщений (см. отчёт пользователя из обратной связи спринта 02). Поэтому `Executor.run` принимает `history` явным параметром и склеивает финальный список сообщений как:

```
[system_prompt] + history + [user: goal]?
```

Порядок и инвариант:

1. Адаптер (Telegram-handler `messages.py`) вызывает `ConversationStore.add_user_message(user_id, text)` **до** `core.handle_user_task` — то есть текущий запрос уже лежит последним элементом в `history`.
2. `core.handle_user_task` достаёт `history = conversations.get_history(user_id)` и передаёт его в `Executor.run` целиком.
3. `Executor.run` собирает `messages = [system] + history`. Если последний элемент `history` уже совпадает с `{"role": "user", "content": goal}` — дубликат не добавляется; иначе (например, тестовый сценарий без адаптера) `goal` дописывается отдельным `user`-сообщением.
4. Внутрицикловые `assistant`/`Observation`-пары копятся в локальном списке `messages` Executor'а и **не** пишутся в `ConversationStore`. В долгую краткосрочную историю попадает только финальный ответ ассистента — его дописывает адаптер после возврата `Executor.run` (`add_assistant_message`).

```
ConversationStore                       Executor.run
[user: «Привет, я Радиф»]    ─────►    messages = [system,
[assistant: «Привет, Радиф»]                       user: «Привет, я Радиф»,
[user: «Как меня зовут?»]                          assistant: «Привет, Радиф»,
                                                   user: «Как меня зовут?»]
       ▲
       │
       └── add_assistant_message(«Тебя зовут Радиф») ◄── финальный ответ Executor.run
```

Лимит длины истории защищён существующим `HISTORY_MAX_MESSAGES` (FIFO в `ConversationStore`) и `HISTORY_SUMMARY_THRESHOLD` (in-session суммаризация — см. §2.3).

### 2.5 Полный лог сессии (`_session_log`)

**Проблема**, которую решает этот буфер (обратная связь пользователя, спринт 02): in-session суммаризация (`replace_with_summary`, §2.3) разрушает `_messages` до `summary + last 2`. Если «/new» архивировал бы именно `_messages`, ранние реплики (например, «Привет, я Радиф») в долгосрочную память не попадают и `memory_search` их не находит после `/new`.

**Решение**: параллельно с `_messages` ведётся append-only буфер `_session_log` — все `user`/`assistant` сообщения текущей сессии в исходном виде, без сжатия и без FIFO-усечения по `HISTORY_MAX_MESSAGES`.

Инварианты:

1. `add_user_message(user_id, text)` и `add_assistant_message(user_id, text)` дублируют запись: одновременно в `_messages` (как раньше) и в `_session_log`.
2. `add_system_message` и `replace_with_summary` — **не трогают** `_session_log`. Это оптимизации контекста для LLM, они не относятся к исходному диалогу.
3. `get_session_log(user_id)` возвращает независимую копию (внешние мутации не влияют на стор).
4. `clear(user_id)` и `rotate_conversation_id(user_id)` **обнуляют** лог пользователя — новая сессия начинается с пустого лога.
5. Верхняя страховка `Settings.session_log_max_messages` (env `SESSION_LOG_MAX_MESSAGES`, default 1000): при переполнении — отбрасывается голова лога и выдаётся `WARNING`. Это редкий сценарий (аномально длинная сессия без `/new`).

**Инвариант высокого уровня**: in-session compaction оптимизирует только контекст для LLM (`_messages`); долгосрочная память при `/new` всегда видит сессию целиком (`_session_log`).

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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    chat_id         INTEGER NOT NULL,
    conversation_id TEXT    NOT NULL,
    chunk_index     INTEGER NOT NULL,
    created_at      TEXT    NOT NULL,         -- ISO 8601
    text            TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_memory_user ON memory_chunks(user_id);
CREATE INDEX IF NOT EXISTS ix_memory_conv ON memory_chunks(conversation_id);

-- векторы (sqlite-vec virtual table)
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0 (
    embedding float[768]
);
```

Связь: `memory_chunks.id == memory_vec.rowid` (используем общий rowid).

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

1. `core.handle_user_task` обнаруживает, что после `add_user_message` история содержит ровно один элемент (новая или сброшенная сессия).
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

## 4. Что НЕ хранится (по дизайну)

- **Сырые сообщения диалога** — только саммари, и только при `/new` (CON-1).
- **Системные промпты** — они в `_prompts/`, не в БД.
- **Вызовы tools и observations** — они в логах, не в архивной памяти.
- **Учётные записи Telegram / профили пользователей** — для MVP не нужны (`user_id` Telegram достаточно как ключ).

## 5. Что **может** появиться в архиве в будущем (НЕ MVP)

(см. `roadmap.md`)

- **Per-skill memory** — отдельная пространственная коллекция чанков для каждого скилла.
- **Per-task memory** — пишем в архив краткое резюме каждой выполненной задачи, чтобы Critic мог сравнивать.
- **TTL и очистка**: автоматическое удаление чанков старше N дней.
- **Поиск с metadata-фильтрами** (по дате, conversation_id и т. п.) через `WHERE` в SQL — `sqlite-vec` это поддерживает, но контракт tool `memory_search` пока не использует.

## 6. Тестируемые свойства

(Чек-лист для `tests/services/test_memory.py` и `tests/services/test_archiver.py` в Спринте 01.)

- `SemanticMemory.init()` создаёт обе таблицы; повторный вызов идемпотентен.
- `SemanticMemory.insert(...)` пишет одну строку в `memory_chunks` и одну запись в `memory_vec`; rowid'ы совпадают.
- `SemanticMemory.search(embedding, top_k=K)` возвращает up-to-K строк, отсортированных по `distance`.
- Поиск ограничен по `user_id` — чужие чанки не возвращаются.
- `Archiver.archive(...)` корректно режет резюме на чанки нужного размера, считает `chunk_index` от 0.
- Падение `Summarizer.summarize` → `Archiver` бросает понятную ошибку, **не** очищает `ConversationStore`.
- Падение `OllamaClient.embed` на одном из чанков → транзакция откатывается, в `memory_chunks` нет «осиротевших» строк.

Тесты используют `tmp_path` для `.db`-файла; `OllamaClient` мокается, `sqlite-vec` грузится по-настоящему (это часть проверки, что окружение работает).
