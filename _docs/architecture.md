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
- **Слоистая изоляция.** Адаптер (Telegram) → Core → Executor → Tool/LLM/Memory. Слой ниже **не знает** про слой выше: tool не знает про aiogram, memory не знает про executor, executor не знает про Telegram. Это даёт реализуемость FR-10 и расширяемость под новые адаптеры (web, MAX) — `architecture.md` §7.
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

- **Telegram**: `TELEGRAM_BOT_TOKEN`.
- **Ollama (LLM)**: `OLLAMA_BASE_URL`, `OLLAMA_DEFAULT_MODEL`, `OLLAMA_AVAILABLE_MODELS`, `OLLAMA_TIMEOUT`.
- **Ollama (Embedding)**: `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`.
- **Agent loop**: `AGENT_MAX_STEPS`, `AGENT_MAX_OUTPUT_CHARS`.
- **Memory (краткосрочная)**: `HISTORY_MAX_MESSAGES`, `HISTORY_SUMMARY_THRESHOLD`, `SUMMARIZATION_PROMPT`.
- **Memory (долгосрочная)**: `MEMORY_DB_PATH`, `MEMORY_CHUNK_SIZE`, `MEMORY_CHUNK_OVERLAP`, `MEMORY_SEARCH_TOP_K`.
- **Prompts**: `AGENT_SYSTEM_PROMPT_PATH`.
- **Logging**: `LOG_LEVEL`, `LOG_FILE`, `LOG_LLM_CONTEXT`.

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

- **`ConversationStore`** — in-memory `user_id → list[{role, content}]` + `user_id → conversation_id`. API: `get_history`, `add_user_message`, `add_assistant_message`, `replace_with_summary(summary, kept_tail=2)`, `clear`, `current_conversation_id`, `rotate_conversation_id`. Жёсткий лимит `Settings.history_max_messages` (FIFO). `get_history` отдаёт **копию**.
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

### 3.9 Prompts (`app/services/prompts.py`, `_prompts/`)

- **`PromptLoader`** при старте процесса читает `AGENT_SYSTEM_PROMPT_PATH` (`_prompts/agent_system.md`) и `_prompts/summarizer.md`. Хранит их как строки. Plug-точки `{{TOOLS_DESCRIPTION}}` и `{{SKILLS_DESCRIPTION}}` подставляются в момент сборки промпта (при инициализации Executor) — см. `prompts.md` §3.

### 3.10 Core (`app/core/orchestrator.py`)

В MVP — тонкая прослойка-функция `async def handle_user_task(text: str, *, user_id: int, chat_id: int, conversations, executor, model=None) -> str`, которая:

1. Берёт текущий `conversation_id` из `ConversationStore`.
2. Достаёт `history = conversations.get_history(user_id)` (адаптер уже дописал текущий user-message в `ConversationStore` до вызова core, см. `memory.md` §2.4).
3. Запускает `Executor.run(goal=text, user_id=..., conversation_id=..., history=history)`.
4. Возвращает финальный текст.

В архитектурном смысле это **единственная точка входа от любого адаптера** (Telegram сейчас, web/MAX в будущем). Адаптер не знает про Executor напрямую.

### 3.11 Executor (`app/agents/executor.py`)

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
            observation = await self.tools.execute(parsed.action, parsed.args, ctx=...)
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "tool", "content": observation})
        return self._max_steps_message()
```

### 3.12 Telegram-адаптер (`app/adapters/telegram/`)

- `handlers/commands.py`: `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`.
- `handlers/messages.py`: обработчик произвольного текста — вызывает `core.handle_user_task` и отдаёт результат.
- `handlers/errors.py`: глобальный error handler.
- `middlewares/logging_mw.py`: логирует каждый апдейт.

Адаптер **не знает** про executor / tools / memory напрямую — только про `core.handle_user_task`, `ConversationStore`, `UserSettingsRegistry`, `Archiver`.

## 4. Поток обработки текстового сообщения (без команды)

1. aiogram получает `Message` через polling.
2. `LoggingMiddleware` логирует входящий апдейт.
3. Router направляет в `messages.py:handle_text`.
4. Handler:
   1. Проверяет длину ввода (`MAX_INPUT_LENGTH = 4000`); при превышении — подсказка и выход.
   2. Берёт `model` и `system_prompt` из `UserSettingsRegistry` (per-user override).
   3. Дописывает сообщение пользователя в `ConversationStore`.
   4. Запускает `bot.send_chat_action(ChatAction.TYPING)`.
   5. Вызывает `core.handle_user_task(text, user_id=..., chat_id=...)`.
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
2. Если история пустая → ответ «Архивировать нечего, новая сессия открыта»; просто ротируем `conversation_id`.
3. Иначе вызываем `Archiver.archive(history, conversation_id, user_id)`:
   1. `Summarizer.summarize(history)` → текст резюме.
   2. Резюме режется на чанки `(MEMORY_CHUNK_SIZE, MEMORY_CHUNK_OVERLAP)`.
   3. Для каждого чанка `OllamaClient.embed(chunk)` → вектор.
   4. `SemanticMemory.insert(chunk, embedding, metadata)` — `metadata` включает `conversation_id`, `chat_id`, `created_at`, `chunk_index`.
4. `ConversationStore.clear(user_id)` + `rotate_conversation_id(user_id)`.
5. Пользователю — сообщение «Архивировано N чанков, новая сессия открыта».
6. Если суммаризация / эмбеддинг упали — `WARNING`, история не очищается (чтобы не потерять контекст), пользователь получает сообщение «Архивирование не удалось, попробуйте ещё раз».

## 6. Обработка ошибок

| Сценарий                                    | Действие                                                                  |
|---------------------------------------------|---------------------------------------------------------------------------|
| Ollama недоступна (connection refused)      | Лог ERROR, сообщение «LLM сейчас недоступна, попробуйте позже».            |
| Таймаут LLM-запроса                         | Лог WARNING, сообщение «Модель слишком долго отвечает».                    |
| Неизвестная модель / 404                    | Лог ERROR, сообщение «Модель не найдена, выберите через /models».          |
| Битый JSON ответа модели                    | Лог WARNING + сырой ответ; цикл прерывается, пользователь — «Модель ответила в неожиданном формате, попробуйте ещё раз». |
| Tool вернул ошибку                          | `observation = "Tool error: <msg>"`; цикл продолжается.                    |
| Превышен `AGENT_MAX_STEPS`                  | Лог INFO, сообщение «Агент не смог решить задачу за N шагов, попробуйте переформулировать». |
| Sqlite-vec не загружается / БД повреждена  | Лог ERROR при старте; долгосрочная память отключается, агент работает без `memory_search` (он возвращает «Долгосрочная память недоступна»). |
| Пустой / слишком длинный ввод               | Сообщение-подсказка пользователю.                                          |
| Необработанное исключение handler           | Перехват в глобальном `errors.py`, лог, нейтральный ответ.                 |

## 7. Расширяемость

### 7.1 Новый tool

1. Создать `app/tools/<name>.py` по контракту из `tools.md` §2.
2. Зарегистрировать в `app/tools/registry.py`.
3. Описание автоматически попадёт в `{{TOOLS_DESCRIPTION}}` системного промпта.
4. Покрыть unit-тестом в `tests/tools/test_<name>.py`.

### 7.2 Новый skill

1. Создать `_skills/<name>/SKILL.md` с первой строкой `Description: ...`.
2. Перезапустить процесс — `SkillRegistry` подхватит автоматически.
3. Описание попадёт в `{{SKILLS_DESCRIPTION}}` системного промпта; агент сможет вызвать `load_skill("<name>")` для получения тела.

### 7.3 Мульти-агент (Planner / Critic) — будущий спринт

`Executor` сейчас — единственный агент. Расширение:

1. Добавить `app/agents/planner.py` — агент, который превращает задачу в план шагов (DAG).
2. Добавить `app/agents/critic.py` — агент, который оценивает финальный ответ Executor (PASS/REVISE).
3. Расширить `Core` (`orchestrator.py`): `task → planner → executor (per-step) → critic → final`. Вместо текущей прямой передачи в `Executor`.
4. **Ничего не меняется** на уровнях tools / memory / skills / Telegram-адаптера. Это и есть точка изоляции NFR-10.

### 7.4 Новый адаптер (web, MAX)

1. Создать `app/adapters/<channel>/` с собственным «приёмником» (FastAPI handler / MAX webhook).
2. Адаптер вызывает `core.handle_user_task(text, user_id=..., chat_id=...)` — тот же контракт, что у Telegram.
3. **Ничего не меняется** в core / agents / tools / memory. Это NFR-11.

### 7.5 Webhook вместо polling

Заменяется код запуска в `app/main.py` (вместо `start_polling` — `aiohttp` / `aiogram`-webhook сервер). Сервис-слой не страдает.

## 8. Конкурентность и производительность

- aiogram + `asyncio` обрабатывает несколько апдейтов конкурентно.
- HTTP-клиент к Ollama — один на приложение (shared `AsyncClient`).
- `sqlite-vec` — через `sqlite3` в connection pool из одного соединения (все операции из одного event loop'а; параллельные write — не нужны для нашего объёма).
- Ollama сама сериализует запросы к модели (узкое место — GPU/CPU), но event loop не блокируется.

## 9. Точки наблюдаемости

- INFO-строка middleware на каждый апдейт: `user`, `chat`, `type`, `dur_ms`, `status`.
- INFO-строка LLM-клиента на каждый вызов: `model`, `len_in`, `len_out`, `dur_ms`, `status`.
- INFO-строка Executor на каждый шаг: `step=<n> kind=thought|action|final user=<id> tool=<name> dur_ms=<n>`.
- INFO-строка Archiver на `/new`: `user=<id> conversation=<id> chunks=<n> dur_ms=<n>`.
- Опциональный лог полного payload LLM (управляется `LOG_LLM_CONTEXT`).

В будущем точки фактически готовы под Prometheus / OpenTelemetry — соответствующая интеграция в roadmap.

## 10. Что архитектура **не делает** (по дизайну)

- Не использует БД, кроме `sqlite-vec` (одного `.db`-файла).
- Не персистит сырые сообщения диалога.
- Не работает с облачными LLM.
- Не использует webhook в MVP.
- Не парсит мультимодальный ввод (фото / аудио / документы) в MVP.
- Не имеет UI кроме Telegram (web — будущий спринт).
