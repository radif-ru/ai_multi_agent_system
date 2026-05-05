# Архитектура

## 1. Общая схема

Telegram-адаптер принимает текст, оборачивает его в задачу, передаёт **исполнителю агентного цикла** (Executor). Executor крутит `thought → action → observation` до `final_answer` или лимита шагов, дёргая LLM (Ollama) и tools (инструменты). На `/new` старая сессия суммируется и складывается в **долгосрочную семантическую память** (`sqlite-vec`).

```
                +----------------------+
                |     Telegram User    |
                +-----------+----------+
                            |
                            | текстовое сообщение / команда
                            v
                +----------------------+
                |   Telegram Bot API   |
                +-----------+----------+
                            |
                            | long polling
                            v
                +----------------------+        +----------------------------+
                |   aiogram Bot        |<-----> |  ConversationStore         |
                |   (Dispatcher,       | read/  |  (in-memory per-user       |
                |    Router, Handlers) | write  |   history, FIFO + summary) |
                +-----------+----------+        +----------------------------+
                            |
                            | task.create(goal, user_id, conversation_id)
                            v
                +----------------------+
                |   Core / Orchestrator|        (в MVP — функция в app/core/orchestrator.py;
                |   (routing only)     |         в будущем — мульти-процесс или мульти-агент)
                +-----------+----------+
                            |
                            v
                +----------------------+
                |   Executor Agent     |  thought → action → observation → ...
                |   (agent loop)       |
                +-----+----------+-----+
                      |          |
            LLM call  |          | tool.execute(name, args)
                      v          v
        +----------------+   +-------------------+
        |  OllamaClient  |   |   Tool Registry   |
        |  .chat(...)    |   |  calculator       |
        |                |   |  read_file        |
        |                |   |  http_request     |
        |                |   |  web_search       |
        |                |   |  memory_search ---+----> SemanticMemory
        |                |   |  load_skill ------+----> SkillRegistry
        +-------+--------+   +-------------------+         |        |
                |                                          v        v
                | HTTP                               +----------+ +----------+
                v                                    |sqlite-vec| | _skills/ |
        +----------------+                           |  KNN     | |          |
        | Ollama (local) |                           +----------+ +----------+
        | qwen3.5:4b +   |
        | nomic-embed... |
        +----------------+
```

Обратный путь: финальный ответ Executor → Core → Telegram-адаптер → `bot.send_message` → пользователь. Ошибка любого слоя → понятное сообщение пользователю + запись в лог.

## 2. Принципы

- **Local-first.** Только локальная Ollama, никаких облачных LLM. Без доступа к интернету проект должен запускаться и решать локальные задачи (поиск тогда падает понятной ошибкой, остальное работает).
- **Слоистая изоляция.** Адаптер (Telegram) → Core → Executor → Tool/LLM/Memory. Слой ниже **не знает** про слой выше: tool не знает про aiogram, memory не знает про executor, executor не знает про Telegram. Это даёт реализуемость FR-10 и расширяемость под новые адаптеры (web, MAX) — `architecture.md` §8.
- **Структурированный диалог с моделью.** Ответ LLM в цикле — **строго JSON** одной из двух форм. Никаких prose-ответов в цикле. См. `agent-loop.md`.
- **Memory split.** Краткосрочная память — in-memory per-user (`ConversationStore`), теряется при рестарте. Долгосрочная — `sqlite-vec` (`SemanticMemory`), пополняется только саммари (не сырыми сообщениями) при `/new`. См. `memory.md`.
- **Tools as a registry.** Каждый tool — отдельный модуль с фиксированным контрактом (`name`, `description`, `args_schema`, `async run(args, ctx) -> str`). Регистрация — централизованная в `app/tools/registry.py`. См. `tools.md`.
- **Skills как промпт-инжект.** `_skills/<name>/SKILL.md` — markdown-инструкции; в системный промпт инжектируется только их описание (первая строка), полное содержание подгружается агентом по требованию через tool `load_skill`. См. `skills.md`.
- **Async-first.** `async/await` сверху донизу. Никаких синхронных HTTP / `time.sleep` в hot path.
- **Polling, не webhook.** Соответствует CON-4. Webhook отложен в roadmap.
- **Отказоустойчивость.** Любая ошибка (таймаут LLM, сетевой сбой, недоступность Ollama, битый JSON, упавший tool, превышение лимита шагов) ловится и превращается в понятное сообщение пользователю + запись в лог.
- **Конфигурация через env.** Все настройки — из переменных окружения через `pydantic-settings`.

## 3. Компоненты

### 3.1 Точка входа (`app/main.py` / `app/__main__.py`)

- Загружает конфигурацию (`Settings`).
- Поднимает логирование.
- Создаёт долгоживущие сервисы: `OllamaClient`, `ConversationStore`, `Summarizer`, `SemanticMemory`, `SkillRegistry`, `PromptLoader`, `ToolRegistry`, `Executor`.
- Создаёт `Bot`, `Dispatcher`, прокидывает зависимости в `dispatcher["..."]` (DI aiogram 3).
- Регистрирует роутеры адаптера (`commands`, `messages`, `errors`) и middleware (`LoggingMiddleware`).
- Регистрирует команды в Telegram UI через `bot.set_my_commands(...)`.
- Запускает polling, в `finally` корректно закрывает клиенты.

### 3.2 Конфигурация (`app/config.py`)

Класс `Settings(BaseSettings)` на `pydantic-settings`. Полный список полей и валидаторов — в `stack.md` §9. Ключевые блоки:

- **Telegram**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_MAX_FILE_MB` (default 20).
- **Ollama (LLM)**: `OLLAMA_BASE_URL`, `OLLAMA_DEFAULT_MODEL`, `OLLAMA_AVAILABLE_MODELS`, `OLLAMA_TIMEOUT`.
- **Ollama (Embedding)**: `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`.
- **Agent loop**: `AGENT_MAX_STEPS`, `AGENT_MAX_OUTPUT_CHARS`.
- **Memory (краткосрочная)**: `HISTORY_MAX_MESSAGES`, `HISTORY_SUMMARY_THRESHOLD`, `SUMMARIZATION_PROMPT`.
- **Memory (долгосрочная)**: `MEMORY_DB_PATH`, `MEMORY_CHUNK_SIZE`, `MEMORY_CHUNK_OVERLAP`, `MEMORY_SEARCH_TOP_K`.
- **Промпты**: `AGENT_SYSTEM_PROMPT_PATH`.
- **Логирование**: `LOG_LEVEL`, `LOG_FILE`, `LOG_LLM_CONTEXT`.
- **Временные файлы**: `TMP_BASE_DIR` (default `data/tmp`). Для каждого пользователя создаётся отдельный подкаталог по `user_id`.
- **Whisper (STT)**: `WHISPER_MODEL` (default `base`), `WHISPER_LANGUAGE` (default `ru`).
- **Vision**: `VISION_MODEL` (default `gemma3:4b`). См. `_docs/vision-models.md` — сравнение лёгких моделей для локального запуска.

Валидация: `OLLAMA_DEFAULT_MODEL ∈ OLLAMA_AVAILABLE_MODELS`, `HISTORY_SUMMARY_THRESHOLD ≤ HISTORY_MAX_MESSAGES`, оба `> 0`, `EMBEDDING_DIMENSIONS > 0`, путь `AGENT_SYSTEM_PROMPT_PATH` существует.

### 3.3 Логирование (`app/logging_config.py`)

`logging.config.dictConfig` с двумя handler'ами: консоль и файл (`RotatingFileHandler`). Формат: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`. Уровень — из `LOG_LEVEL`. Файл — `LOG_FILE`, каталог создаётся автоматически. См. `_docs/agent-loop.md` §6 про логирование шагов цикла.

### 3.4 LLM-сервис (`app/services/llm.py`)

Класс `OllamaClient` (async, на `ollama.AsyncClient`).

- `chat(messages: list[dict], *, model: str, temperature: float = 0.0) -> str` — основной путь: список сообщений `[{"role", "content"}, ...]`, на возврат — текстовый ответ модели.
- `embed(text: str, *, model: str) -> list[float]` — эмбеддинг текста через `ollama.AsyncClient.embeddings`.
- Иерархия исключений: `LLMError` → `LLMTimeout`, `LLMUnavailable`, `LLMBadResponse`.
- Маппинг: `httpx.TimeoutException` / `asyncio.TimeoutError` → `LLMTimeout`; `httpx.ConnectError` → `LLMUnavailable`; `ollama.ResponseError` 404 → `LLMBadResponse("модель не найдена")`; прочие 4xx/5xx → `LLMBadResponse`; пустой ответ → `LLMBadResponse`.
- На каждый вызов пишет INFO-строку с метриками (`model`, `len_in`, `len_out`, `dur_ms`, `status`).
- `estimate_tokens(value: str | list[dict]) -> int` — приближённая оценка `chars / 4` (для логирования размера контекста).

### 3.5 Краткосрочная память (`app/services/conversation.py`, `app/services/summarizer.py`)

- **`ConversationStore`** — in-memory `user_id → list[{role, content}]` + `user_id → conversation_id`. API: `get_history`, `get_session_log`, `add_user_message`, `add_assistant_message`, `replace_with_summary(summary, kept_tail=2)`, `clear`, `current_conversation_id`, `rotate_conversation_id`. Жёсткий лимит `Settings.history_max_messages` (FIFO). `get_history` отдаёт **копию**. Внутри стора два буфера: rolling-`_messages` (с in-session compaction для LLM-контекста) и параллельный append-only `_session_log` (полный лог текущей сессии для `/new` → `Archiver`, страховка `Settings.session_log_max_messages`); `replace_with_summary` `_session_log` не трогает. См. `memory.md` §2.5.
- **`Summarizer`** — обёртка над `OllamaClient.chat`, сжимает историю в краткое резюме (`Settings.summarization_prompt`). Используется в двух местах:
  1. **In-session** (когда `len(history) >= history_summary_threshold`) — заменяет старую часть истории резюме (`replace_with_summary`).
  2. **При архивировании** (`/new`) — суммирует всю сессию, дальше архиватор режет на чанки и пишет в `SemanticMemory`.

### 3.6 Долгосрочная память (`app/services/memory.py`, `app/services/archiver.py`)

- **`SemanticMemory`** — обёртка над SQLite + `sqlite-vec`. API: `init()` (создаёт схему и `vec0` таблицу), `insert(chunk_text, embedding, metadata)`, `search(embedding, top_k)`. Ключевые поля: `id`, `chat_id`, `conversation_id`, `chunk_index`, `created_at`, `text`, `embedding` (`vec0`-колонка). Подробности схемы — в `memory.md` §5.
- **`Archiver`** — оркестратор для команды `/new`: берёт историю текущей сессии, вызывает `Summarizer`, режет результат на чанки (`MEMORY_CHUNK_SIZE` / `MEMORY_CHUNK_OVERLAP`), для каждого получает `OllamaClient.embed(...)`, пишет в `SemanticMemory`, затем сбрасывает in-memory историю и ротирует `conversation_id`.

### 3.7 Tools (`app/tools/`)

- **`registry.py`** — `ToolRegistry` со статическим набором tools. API: `get(name)`, `list_descriptions() -> list[{name, description}]`, `execute(name, args, ctx) -> str`.
- **Контракт tool** (`app/tools/base.py`):
  - `name: str` (snake_case, уникальное).
  - `description: str` (короткое, идёт в системный промпт).
  - `args_schema: dict` (JSON Schema для валидации `args`).
  - `async run(args: dict, ctx: ToolContext) -> str` — возврат — текст для `observation`.
- **MVP-набор**: `calculator.py`, `read_file.py`, `http_request.py`, `web_search.py`, `memory_search.py`, `load_skill.py`. Подробно — в `tools.md`.

### 3.8 Skills (`app/services/skills.py`, `_skills/`)

- **`SkillRegistry`** сканирует каталог `_skills/`, для каждой подпапки с `SKILL.md` парсит первую строку (`Description: ...`), остальное держит в памяти как тело скилла.
- API: `list_descriptions() -> list[{name, description}]` (для инжекции в системный промпт), `get_body(name) -> str` (для tool `load_skill`).
- Перезагрузка не требуется в MVP — скиллы читаются один раз при старте процесса. Hot-reload — кандидат на отдельный спринт.

### 3.9 Пользователи (`app/users/`)

- **`User`** — dataclass с полями `id: int` (внутренний автоинкремент), `channel: str` ("telegram" или "console"), `external_id: str` (внешний идентификатор в канале), `display_name: str | None`, `created_at: datetime`.
- **`UserRepository`** — in-memory репозиторий, единственная точка «получить или создать» пользователя по внешнему ключу. API: `async get_or_create(channel, external_id, display_name) -> tuple[User, bool]`, `async get(user_id) -> User | None`, `async get_by_external(channel, external_id) -> User | None`. Потокобезопасность через `asyncio.Lock`. В будущем будет использоваться для публикации события `UserCreated` и для идентификации пользователей в адаптерах.

### 3.10 Prompts (`app/services/prompts.py`, `_prompts/`)

- **`PromptLoader`** при старте процесса читает `AGENT_SYSTEM_PROMPT_PATH` (`_prompts/agent_system.md`) и `_prompts/summarizer.md`. Хранит их как строки. Plug-точки `{{TOOLS_DESCRIPTION}}` и `{{SKILLS_DESCRIPTION}}` подставляются в момент сборки промпта (при инициализации Executor) — см. `prompts.md` §3.

### 3.11 Core (`app/core/orchestrator.py`)

В MVP — тонкая прослойка-функция `async def handle_user_task(text: str, *, user_id: int, chat_id: int, conversations, executor, model=None) -> str`, которая:

1. Берёт текущий `conversation_id` из `ConversationStore`.
2. Достаёт `history = conversations.get_history(user_id)` (адаптер уже дописал текущий user-message в `ConversationStore` до вызова core, см. `memory.md` §2.4).
3. Если это первый ход новой сессии (`len(history) == 1`) и `SESSION_BOOTSTRAP_ENABLED=true` — делает авто-подгрузку архива через `SemanticMemory.search` и дописывает найденные чанки `system`-сообщением в начало `history` (см. `memory.md` §3.6). Падение embed/search — `WARNING`, ход продолжается.
4. Запускает `Executor.run(goal=text, user_id=..., conversation_id=..., history=history)`.
5. Возвращает финальный текст.

В архитектурном смысле это **единственная точка входа от любого адаптера** (Telegram сейчас, web/MAX в будущем). Адаптер не знает про Executor напрямую.

### 3.12 Executor (`app/agents/executor.py`)

Реализует агентный цикл `thought → action → observation`. Контракт — в `agent-loop.md`. Кратко:

```python
class Executor:
    async def run(
        self,
        *,
        goal: str,
        user_id: int,
        conversation_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        # См. `memory.md` §2.4 о склейке истории.
        messages = self._build_initial_messages(goal, history)
        for step in range(self.settings.agent_max_steps):
            response_text = await self.llm.chat(messages, model=...)
            parsed = parse_agent_response(response_text)  # JSON or LLMBadResponse
            if parsed.is_final:
                return parsed.final_answer
            # action → observation → messages.append(...)
```

- **Автоматическая суммаризация контекста:** перед отправкой в LLM проверяется размер контекста (суммарно). Если превышает `AGENT_MAX_CONTEXT_CHARS` (default 8000), история автоматически суммаризируется через `Summarizer`. Это предотвращает пустые ответы LLM при больших контекстах (например, при обработке PDF с OCR текстом).
- **Логирование аргументов tools:** при вызове любого tool логируются все переданные аргументы для отладки.

### 3.13 Telegram-адаптер (`app/adapters/telegram/`)

- `handlers/commands.py`: `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`.
- `handlers/messages.py`: обработчик произвольного текста и файлов — вызывает `core.handle_user_task` и отдаёт результат. Поддерживает три типа файлов:
  - `handle_document`: обрабатывает `Document` сообщения (PDF/TXT/MD). Скачивает файл, формирует обогащённый goal с путём к файлу и caption, передаёт в `core.handle_user_task` (агент использует tool `read_document`).
  - `handle_voice`: обрабатывает `Voice`/`Audio` сообщения. Скачивает файл, транскрибирует через `Transcriber` (faster-whisper), передаёт распознанный текст в `core.handle_user_task`.
  - `handle_photo`: обрабатывает `Photo` сообщения. Скачивает файл, описывает через `Vision` (Ollama vision API), передаёт описание в `core.handle_user_task`.
- `handlers/errors.py`: глобальный error handler.
- `middlewares/logging_mw.py`: логирует каждый апдейт.
- `files.py`: утилита `download_telegram_file` для скачивания файлов из Telegram с проверкой размера и лимитов.

Адаптер **не знает** про executor / tools / memory напрямую — только про `core.handle_user_task`, `ConversationStore`, `UserSettingsRegistry`, `Archiver`.

## 4. Поток обработки текстового сообщения (без команды)

1. aiogram получает `Message` через polling.
2. `LoggingMiddleware` логирует входящий апдейт.
3. Router направляет в `messages.py:handle_text`.
4. Handler:
   1. Проверяет длину ввода (`MAX_INPUT_LENGTH = 4000`); при превышении — подсказка и выход.
   2. **Reply-обработка:** если сообщение является ответом (`message.reply_to_message`), текст оригинального сообщения включается в контекст в формате `[В ответ на: <текст оригинала>]\n<текст ответа>`. Длинные оригиналы обрезаются до 500 символов. Это позволяет агенту понимать контекст ответа.
   3. Берёт `model` и `system_prompt` из `UserSettingsRegistry` (per-user override).
   4. Дописывает сообщение пользователя в `ConversationStore`.
   5. Запускает `bot.send_chat_action(ChatAction.TYPING)`.
   6. Вызывает `core.handle_user_task(text, user_id=..., chat_id=...)`.
5. Core берёт `conversation_id` из `ConversationStore` и вызывает `Executor.run(...)`.
6. Executor крутит цикл (см. §3.11) до финального ответа или лимита шагов.
7. Core возвращает финальный текст в handler.
8. Handler:
   1. Дописывает ответ ассистента в `ConversationStore`.
   2. **Условная in-session суммаризация**: если `len(history) >= history_summary_threshold`, вызывает `Summarizer.summarize(history[:-2])` и пишет результат через `replace_with_summary(..., kept_tail=2)`. Падение суммаризации → `WARNING`, ответ пользователю не страдает.
   3. Отправляет ответ пользователю (`message.answer`), при необходимости разбивая на части > 4096 символов.
9. При ошибке любого слоя — человекочитаемое сообщение пользователю + запись в лог.

## 5. Поток `/new` (архивирование сессии)

1. Handler `/new` берёт текущий `conversation_id` и историю из `ConversationStore`.
2. Если история пустая → ответ «Сессия пустая, новая открыта»; просто ротируем `conversation_id`.
3. Иначе вызываем `Archiver.archive(history, conversation_id, user_id, progress_callback)`:
   1. `Summarizer.summarize(history)` → текст резюме (map-reduce для длинных сессий).
      - Лог: `archive stage=summarize dur_ms=N`
   2. Резюме режется на чанки `(MEMORY_CHUNK_SIZE, MEMORY_CHUNK_OVERLAP)`.
      - Лог: `archive stage=chunking chunks=N dur_ms=N`
   3. **Параллельный embedding**: чанки обрабатываются через `asyncio.gather` с семафором `EMBEDDING_CONCURRENCY` (default 5).
      - Лог: `archive stage=embedding chunks=N dur_ms=N`
   4. `SemanticMemory.insert(chunk, embedding, metadata)` — `metadata` включает `conversation_id`, `chat_id`, `chunk_index`.
      - Лог: `archive stage=database chunks=N dur_ms=N`
   5. **Прогресс**: при `progress_callback` пользователю показываются этапы («Суммирую…», «Создаю эмбеддинги…»).
4. `ConversationStore.clear(user_id)` + `rotate_conversation_id(user_id)`.
5. Пользователю — сообщение «Архивировано N чанков, новая сессия открыта».
6. Если суммаризация / эмбеддинг упали — `WARNING`, история не очищается (чтобы не потерять контекст), пользователь получает сообщение «Архивирование не удалось: <error>. Сессия сохранена, попробуйте /new ещё раз позже».
7. Итоговое логирование: `archive ok user_id=N conv=<id> chunks=N total_dur_ms=N`.

## 6. Поток обработки файлов (Document, Voice, Photo)

Система поддерживает три типа файлов из Telegram: документы (PDF/TXT/MD), голосовые сообщения (Voice/Audio) и фотографии (Photo). Все файлы скачиваются во временную директорию (`Settings.tmp_base_dir`, default `data/tmp`), в подкаталог пользователя по `user_id`, обрабатываются соответствующими сервисами, а результат передаётся в агентный цикл как обычный текст.

### 6.1 Общие компоненты

- **`download_telegram_file`** (`app/adapters/telegram/files.py`): async-утилита для скачивания файлов из Telegram. Проверяет размер файла до скачивания (`TELEGRAM_MAX_FILE_MB`, default 20), выбрасывает `FileTooLargeError` при превышении. Скачивает в `tempfile.NamedTemporaryFile` с авто-очисткой.
- **`Settings.tmp_base_dir`**: базовая директория для временных файлов (создаётся автоматически при старте, default `data/tmp`). Для каждого пользователя создаётся отдельный подкаталог по `user_id`. Все операции чтения файлов ограничены этой директорией для защиты от path traversal.

### 6.2 Handler Document

- **`handle_document`** (`app/adapters/telegram/handlers/messages.py`): обрабатывает `Document` сообщения.
- Поток:
  1. Скачивает файл через `download_telegram_file`.
  2. Формирует обогащённый goal: `«Пользователь прислал документ {path}. Caption: {caption}. Прочитай через read_document и ответь по сути.»`
  3. Передаёт goal в `core.handle_user_task` (агент использует tool `read_document`).
  4. Удаляет временный файл после обработки.
- При превышении лимита размера — сообщение «Файл слишком большой, отправьте файл меньшего размера».

### 6.3 Handler Voice

- **`Transcriber`** (`app/services/transcribe.py`): обёртка над `faster-whisper` для транскрипции речи. Опциональная зависимость — если не установлен, handler отвечает fallback-сообщением.
- **`handle_voice`** (`app/adapters/telegram/handlers/messages.py`): обрабатывает `Voice`/`Audio` сообщения.
- Поток:
  1. Скачивает файл через `download_telegram_file`.
  2. Транскрибирует через `Transcriber.transcribe(path)` → текст.
  3. Передаёт распознанный текст в `core.handle_user_task` как обычное сообщение.
  4. Удаляет временный файл после обработки.
- Конфигурация: `WHISPER_MODEL` (default `base`), `WHISPER_LANGUAGE` (default `ru`).
- При недоступности faster-whisper — сообщение «Распознавание речи недоступно, установите faster-whisper».

### 6.4 Handler Photo

- **`Vision`** (`app/services/vision.py`): обёртка над `OllamaClient.chat` с поддержкой параметра `images` для описания изображений. Кодирует изображение в base64 и передаёт в Ollama vision API.
- **`handle_photo`** (`app/adapters/telegram/handlers/messages.py`): обрабатывает `Photo` сообщения.
- Поток:
  1. Скачивает файл через `download_telegram_file`.
  2. Описывает через `Vision.describe(path, caption)` → текст описания.
  3. Формирует goal с путём к файлу и описанием: `"Изображение: {path}\nОписание: {description}"`.
  4. Передаёт goal в `core.handle_user_task`.
  5. Файл не удаляется сразу — живёт в `tmp/` до `/new` или TTL cleanup (1 час).
- **Tool `describe_image`** (`app/tools/describe_image.py`): агент может вызвать этот tool для повторного описания изображения по пути (например, для уточнения деталей «что написано в углу?»). Валидирует путь (должен быть в `tmp/`, без `..`, существующий файл изображения), затем вызывает `Vision.describe`.
- **Cleanup старых изображений**: при команде `/new` вызывается `_cleanup_tmp_images(tmp_dir)` — удаляет изображения старше 1 часа из `tmp/`.
- Конфигурация: `VISION_MODEL` (default `gemma3:4b`, см. `_docs/vision-models.md`). Если пустая — сообщение «Vision-модель не подключена, отправь текстом, что на картинке».

### 6.5 Tool `read_document`

- **`ReadDocumentTool`** (`app/tools/read_document.py`): tool для чтения документов из временной директории.
- Поддерживаемые форматы: PDF (через `pypdf`), TXT, MD.
- Защита от path traversal: файлы читаются только из `Settings.tmp_base_dir`.
- Усечение вывода до `max_chars` (default 8000).
- **OCR (опционально):** если включён `READ_DOCUMENT_OCR_ENABLED` и установлен tesseract-ocr, для PDF с малым количеством текста (< 100 символов) извлекается текст из изображений через pytesseract. OCR текст кешируется в файл `.ocr.txt` рядом с PDF для ускорения повторного чтения. Поддержка кириллицы через `tesseract-ocr-rus`.
- **Извлечение изображений из PDF:** tool извлекает изображения из PDF (до `READ_DOCUMENT_MAX_EXTRACTED_IMAGES` по умолчанию 10, при OCR включённом до `READ_DOCUMENT_MAX_OCR_IMAGES` по умолчанию 20). Изображения сохраняются во временной директории. Если OCR не сработал, возвращается информация о картинках для описания через `describe_image`.

## 7. Обработка ошибок

| Сценарий                                    | Действие                                                                  |
|---------------------------------------------|---------------------------------------------------------------------------|
| Ollama недоступна (connection refused)      | Лог ERROR, сообщение «LLM сейчас недоступна, попробуйте позже».            |
| Таймаут LLM-запроса                         | Лог WARNING, сообщение «Модель слишком долго отвечает».                    |
| Неизвестная модель / 404                    | Лог ERROR, сообщение «Модель не найдена, выберите через /models».          |
| Битый JSON ответа модели                    | Лог WARNING + сырой ответ; цикл прерывается, пользователь — «Модель ответила в неожиданном формате, попробуйте ещё раз». |
| Tool вернул ошибку                          | `observation = "Tool error: <msg>"`; цикл продолжается.                    |
| Превышен `AGENT_MAX_STEPS`                  | Лог INFO, сообщение «Агент не смог решить задачу за N шагов, попробуйте переформулировать». |
| Пустой ответ LLM (chat empty response)       | Лог WARNING, сообщение «Модель не смогла обработать такой большой запрос. Попробуйте отправить файл меньшего размера или задайте более конкретный вопрос.» |
| Sqlite-vec не загружается / БД повреждена  | Лог ERROR при старте; долгосрочная память отключается, агент работает без `memory_search` (он возвращает «Долгосрочная память недоступна»). |
| Пустой / слишком длинный ввод               | Сообщение-подсказка пользователю.                                          |
| Необработанное исключение handler           | Перехват в глобальном `errors.py`, лог, нейтральный ответ.                 |

## 8. Расширяемость

### 8.1 Новый tool

1. Создать `app/tools/<name>.py` по контракту из `tools.md` §2.
2. Зарегистрировать в `app/tools/registry.py`.
3. Описание автоматически попадёт в `{{TOOLS_DESCRIPTION}}` системного промпта.
4. Покрыть unit-тестом в `tests/tools/test_<name>.py`.

### 8.2 Новый skill

1. Создать `_skills/<name>/SKILL.md` с первой строкой `Description: ...`.
2. Перезапустить процесс — `SkillRegistry` подхватит автоматически.
3. Описание попадёт в `{{SKILLS_DESCRIPTION}}` системного промпта; агент сможет вызвать `load_skill("<name>")` для получения тела.

### 8.3 Мульти-агент (Planner / Critic) — будущий спринт

`Executor` сейчас — единственный агент. Расширение:

1. Добавить `app/agents/planner.py` — агент, который превращает задачу в план шагов (DAG).
2. Добавить `app/agents/critic.py` — агент, который оценивает финальный ответ Executor (PASS/REVISE).
3. Расширить `Core` (`orchestrator.py`): `task → planner → executor (per-step) → critic → final`. Вместо текущей прямой передачи в `Executor`.
4. **Ничего не меняется** на уровнях tools / memory / skills / Telegram-адаптера. Это и есть точка изоляции NFR-10.

### 8.4 Новый адаптер (console, web, MAX)

1. Создать `app/adapters/<channel>/` с собственным «приёмником» (REPL-цикл для консоли, FastAPI handler / MAX webhook для web).
2. Адаптер вызывает `core.handle_user_task(text, user_id=..., chat_id=...)` — тот же контракт, что у Telegram.
3. **Ничего не меняется** в core / agents / tools / memory. Это NFR-11.
4. Пример реализации — консольный адаптер (`app/adapters/console/`), см. `_docs/console-adapter.md`.

### 8.5 Webhook вместо polling

Заменяется код запуска в `app/main.py` (вместо `start_polling` — `aiohttp` / `aiogram`-webhook сервер). Сервис-слой не страдает.

## 9. Конкурентность и производительность

- aiogram + `asyncio` обрабатывает несколько апдейтов конкурентно.
- HTTP-клиент к Ollama — один на приложение (shared `AsyncClient`).
- `sqlite-vec` — через `sqlite3` в connection pool из одного соединения (все операции из одного event loop'а; параллельные write — не нужны для нашего объёма).
- Ollama сама сериализует запросы к модели (узкое место — GPU/CPU), но event loop не блокируется.

## 10. Точки наблюдаемости

- INFO-строка middleware на каждый апдейт: `user`, `chat`, `type`, `dur_ms`, `status`.
- INFO-строка LLM-клиента на каждый вызов: `model`, `len_in`, `len_out`, `dur_ms`, `status`.
- INFO-строка Executor на каждый шаг: `step=<n> kind=thought|action|final user=<id> tool=<name> dur_ms=<n>`.
- INFO-строка Archiver на `/new`: `user=<id> conversation=<id> chunks=<n> dur_ms=<n>`.
- Опциональный лог полного payload LLM (управляется `LOG_LLM_CONTEXT`).

В будущем точки фактически готовы под Prometheus / OpenTelemetry — соответствующая интеграция в roadmap.

## 11. Что архитектура **не делает** (по дизайну)

- Не использует БД, кроме `sqlite-vec` (одного `.db`-файла).
- Не персистит сырые сообщения диалога.
- Не работает с облачными LLM.
- Не использует webhook в MVP.
- Не работает с видео и стримами медиа (принимаются только Document/Voice/Photo, см. §6).
- Не имеет UI кроме Telegram (web — будущий спринт).
