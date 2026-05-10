# Структура проекта

Целевая структура репозитория после реализации Спринта 05 (Безопасность и OCR). На момент Спринта 00 (Bootstrap) большинство `app/`-модулей — пустые файлы с одной декларацией пакета; реальный код появляется задачами Спринта 01+.

```
ai-multi-agent-system/
├── .env.example              # шаблон конфигурации (коммитится)
├── .env                      # реальные секреты (в .gitignore)
├── .gitignore
├── CLAUDE.md                 # поведенческие гайдлайны LLM-агента (общие)
├── README.md                 # инструкция запуска + команды бота
├── requirements.txt          # runtime + dev-зависимости
├── pyproject.toml            # конфиг pytest (asyncio_mode=auto)
│
├── _docs/                    # проектная документация для LLM-агентов и людей
│   ├── README.md             # индекс документации
│   ├── mvp.md                # scope MVP и критерии приёмки (Спринт 01)
│   ├── requirements.md       # FR / NFR / CON / ASM
│   ├── architecture.md       # компоненты, поток данных, мульти-агент в перспективе
│   ├── agent-loop.md         # формат JSON ответа модели и правила цикла
│   ├── memory.md             # краткосрочная и долгосрочная память (sqlite-vec)
│   ├── tools.md              # реестр инструментов и контракт нового tool
│   ├── skills.md             # формат _skills/ и как агент их использует
│   ├── prompts.md            # формат _prompts/ и плейсхолдеры
│   ├── stack.md              # версии, зависимости, переменные окружения
│   ├── instructions.md       # правила разработки (стиль, git, async, тесты)
│   ├── project-structure.md  # этот файл
│   ├── commands.md           # спецификация команд бота
│   ├── testing.md            # стратегия тестирования
│   ├── roadmap.md            # этапы развития, в т.ч. multi-agent
│   ├── current-state.md      # фактическое состояние: легаси, баги, нюансы
│   └── links.md              # каталог внешних ссылок (aiogram, Ollama, sqlite-vec, …)
│
├── _board/                   # процесс и итерации для LLM-агентов
│   ├── README.md             # индекс доски
│   ├── plan.md               # индекс спринтов (только таблицы)
│   ├── process.md            # свод правил и процесса: легенды, шаблоны, §1–§12
│   └── sprints/              # файлы спринтов: <NN>-<short-name>.md
│       ├── 00-bootstrap.md
│       └── 01-mvp-agent.md
│
├── _skills/                  # markdown-скиллы для агента (по одной подпапке на скилл)
│   ├── README.md             # формат и шаблон SKILL.md
│   └── <skill-name>/
│       └── SKILL.md          # первая строка `Description: ...`, далее markdown-инструкция
│
├── _prompts/                 # системные промпты в markdown
│   ├── README.md             # роль каждого файла, как меняется через .env
│   ├── agent_system.md       # главный промпт агентного цикла (с {{TOOLS_DESCRIPTION}}, {{SKILLS_DESCRIPTION}})
│   └── summarizer.md         # промпт для in-memory суммаризации и архивирования
│
├── data/                     # runtime-данные (в .gitignore): sqlite-vec БД, …
│   ├── memory.db             # путь по умолчанию для MEMORY_DB_PATH
│   ├── file_contexts.db      # контексты файлов и маппинги file_id → path
│   └── tmp/                  # временные файлы (изолированы по user_id)
│
├── logs/                     # файлы логов (в .gitignore)
│   └── agent.log
│
├── app/                      # код приложения
│   ├── __init__.py
│   ├── __main__.py           # entrypoint: python -m app
│   ├── main.py               # async def main(): сборка зависимостей, регистрация роутеров, polling
│   ├── config.py             # Settings на pydantic-settings
│   ├── logging_config.py     # dictConfig + RotatingFileHandler
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator.py   # handle_user_task(text, user_id, chat_id) — единая точка входа от любого адаптера
│   │   └── events.py         # EventBus: событийная шина для pub/sub между компонентами
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── executor.py       # агент с циклом thought → action → observation
│   │   └── protocol.py       # парсер JSON ответа модели + AgentDecision dataclass
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py           # Tool, ToolContext, MAX_TOOL_OUTPUT_CHARS
│   │   ├── errors.py         # ToolError, ToolNotFound, ArgsValidationError
│   │   ├── registry.py       # ToolRegistry: list_descriptions, execute
│   │   ├── calculator.py
│   │   ├── read_file.py
│   │   ├── read_document.py  # чтение документов (PDF/TXT/MD/JPG/PNG) с OCR
│   │   ├── describe_image.py # описание изображений через Vision
│   │   ├── ocr_image.py      # OCR для одиночных изображений
│   │   ├── http_request.py
│   │   ├── web_search.py
│   │   ├── memory_search.py
│   │   ├── load_skill.py
│   │   └── weather.py        # погода через wttr.in
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm.py            # OllamaClient (.chat, .embed) + LLMError + estimate_tokens
│   │   ├── conversation.py   # ConversationStore: in-memory история per-user, conversation_id, file_contexts (SQLite)
│   │   ├── summarizer.py     # Summarizer: сжатие истории через LLM
│   │   ├── memory.py         # SemanticMemory: sqlite-vec обёртка (init/insert/search)
│   │   ├── archiver.py       # Archiver: оркестратор /new (summary → chunk → embed → insert)
│   │   ├── skills.py         # SkillRegistry: парсинг _skills/, описания и тела
│   │   ├── prompts.py        # PromptLoader: чтение _prompts/, подстановка плейсхолдеров
│   │   ├── model_registry.py # UserSettingsRegistry: per-user model + system_prompt
│   │   ├── transcribe.py     # Transcriber: обёртка над faster-whisper для транскрипции речи
│   │   ├── vision.py         # Vision: обёртка над OllamaClient.chat с поддержкой images
│   │   ├── ocr.py            # OCR: обёртка над pytesseract для распознавания текста
│   │   ├── conversation_subscriber.py # подписчики EventBus для записи в ConversationStore
│   │   ├── summarizer_subscriber.py # подписчик для in-session суммаризации
│   │   ├── tmp_cleanup.py    # подписчик для очистки tmp-изображений при /new
│   │   └── session_bootstrap.py # авто-подгрузка контекста из SemanticMemory при старте сессии
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── console/
│   │   │   ├── __init__.py
│   │   │   └── adapter.py       # REPL-цикл с теми же командами, что и Telegram-адаптер
│   │   └── telegram/
│   │       ├── __init__.py
│   │       ├── files.py          # download_telegram_file: скачивание файлов из Telegram
│   │       ├── handlers/
│   │       │   ├── __init__.py
│   │       │   ├── commands.py   # /start, /help, /models, /model, /prompt, /new, /reset
│   │       │   ├── messages.py   # F.text & ~F.text.startswith('/') → core.handle_user_task
│   │       │   └── errors.py     # глобальный error handler (router.errors)
│   │       └── __init__.py
│   │
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── logging_mw.py     # LoggingMiddleware (user/chat/type/dur_ms/status)
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── input_sanitizer.py # sanitize_user_input: защита от prompt injection
│   │   ├── file_id_mapper.py  # FileIdMapper: маскирование путей к файлам
│   │   └── response_sanitizer.py # sanitize_response: фильтрация системной информации
│   │
│   ├── users/
│   │   ├── __init__.py
│   │   └── repository.py     # UserRepository: хранилище пользователей с get_or_create
│   │
│   └── utils/
│       ├── __init__.py
│       └── text.py           # split_long_message и пр.
│
└── tests/                    # зеркалит app/
    ├── __init__.py
    ├── conftest.py           # фикстура base_env (изоляция переменных окружения), tmp .db
    ├── test_config.py
    ├── test_logging_config.py
    ├── test_main.py          # smoke-тест сборки main()
    ├── test_middleware_logging.py
    ├── test_utils_text.py
    ├── agents/
    │   ├── __init__.py
    │   ├── test_executor.py
    │   └── test_protocol.py  # парсер JSON
    ├── tools/
    │   ├── __init__.py
    │   ├── test_registry.py
    │   ├── test_calculator.py
    │   ├── test_read_file.py
    │   ├── test_read_document.py
    │   ├── test_http_request.py
    │   ├── test_web_search.py
    │   ├── test_memory_search.py
    │   └── test_load_skill.py
    ├── services/
    │   ├── __init__.py
    │   ├── test_llm_client.py
    │   ├── test_conversation_store.py
    │   ├── test_summarizer.py
    │   ├── test_memory.py
    │   ├── test_archiver.py
    │   ├── test_skills.py
    │   ├── test_prompts.py
    │   └── test_model_registry.py
    ├── security/
    │   ├── __init__.py
    │   └── test_file_id_mapper.py
    ├── core/
    │   ├── __init__.py
    │   └── test_orchestrator.py
    └── adapters/
        ├── console/
        │   └── __init__.py
        └── telegram/
            ├── __init__.py
            ├── test_commands.py
            ├── test_messages.py
            ├── test_documents.py
            ├── test_voice.py
            ├── test_photo.py
            └── test_events.py
```

## Назначение ключевых модулей

| Путь | Ответственность |
|------|-----------------|
| `CLAUDE.md` | Общие поведенческие гайдлайны LLM-агента (think before coding, simplicity, surgical changes, goal-driven). Читается первым перед любой задачей. |
| `_docs/*.md` | Проектная документация: требования, архитектура, стек, инструкции, roadmap, агентный цикл, память, tools, skills, prompts. |
| `_docs/current-state.md` | Фактическое состояние кода: что работает, легаси, известные проблемы. **Читать перед правками.** Технический долг текущего кода — в §2 этого файла. |
| `_docs/links.md` | Каталог внешних ссылок (aiogram, Ollama, sqlite-vec, ddgs, pytest и др.). |
| `_board/plan.md` | Индекс спринтов (активные, закрытые, запланированные). Сами задачи — в `sprints/<NN>-<short-name>.md`. |
| `_board/sprints/` | Каталог файлов спринтов (по одному на спринт); история сохраняется. |
| `_board/process.md` | Свод правил процесса: легенды, правила спринтов и задач, шаблоны, пошаговый алгоритм (§1–§12). |
| `_skills/*/SKILL.md` | Markdown-инструкции для агента (по одной подпапке на скилл; первая строка — `Description: ...`). |
| `_prompts/agent_system.md` | Главный системный промпт цикла, с плейсхолдерами `{{TOOLS_DESCRIPTION}}` / `{{SKILLS_DESCRIPTION}}`. |
| `_prompts/summarizer.md` | Промпт для in-memory суммаризации и для `/new`-архивирования. |
| `data/` | Runtime-данные (БД `sqlite-vec`); путь по умолчанию для `MEMORY_DB_PATH`. В `.gitignore`. |
| `app/__main__.py` | Запуск `asyncio.run(main())`. |
| `app/main.py` | Собирает все сервисы, `Bot`, `Dispatcher`, регистрирует роутеры/middleware, стартует polling. |
| `app/config.py` | Класс `Settings(BaseSettings)`, парсинг `.env`, валидация. |
| `app/logging_config.py` | Функция `setup_logging(settings)` → `dictConfig`. |
| `app/core/orchestrator.py` | `async handle_user_task(...)` — единая точка входа от любого адаптера; вызывает `Executor`. |
| `app/core/events.py` | `EventBus`: событийная шина для pub/sub между компонентами (UserCreated, MessageReceived, ResponseGenerated, ConversationArchived). |
| `app/agents/executor.py` | Агентный цикл `thought → action → observation`. |
| `app/agents/protocol.py` | Парсер JSON ответа модели, dataclass `AgentDecision`, `parse_agent_response(...)`. |
| `app/tools/base.py` | `Tool` Protocol, `ToolContext` Protocol, `MAX_TOOL_OUTPUT_CHARS`. |
| `app/tools/registry.py` | `ToolRegistry`: `get`, `list_descriptions`, `execute` (валидация args, логирование, усечение). |
| `app/tools/calculator.py`, `read_file.py`, `http_request.py`, `web_search.py`, `memory_search.py`, `load_skill.py` | MVP-tools (см. `tools.md` §4). |
| `app/tools/read_document.py` | Чтение документов (PDF/TXT/MD/JPG/PNG) с OCR через pytesseract. |
| `app/tools/describe_image.py` | Описание изображений через Vision API. |
| `app/tools/ocr_image.py` | OCR для одиночных изображений. |
| `app/tools/weather.py` | Погода через wttr.in с fallback на WebSearchTool. |
| `app/services/llm.py` | `OllamaClient` (async) с `chat` и `embed`, `estimate_tokens`, иерархия `LLMError`. |
| `app/services/conversation.py` | `ConversationStore`: in-memory история per-user (`user_id → list`), `conversation_id`, FIFO-обрезка, file_contexts (SQLite). |
| `app/services/summarizer.py` | `Summarizer`: тонкая обёртка над `OllamaClient.chat`. Используется и для in-session порога, и для `/new`. |
| `app/services/memory.py` | `SemanticMemory`: обёртка над `sqlite3 + sqlite_vec.load`; `init`, `insert`, `search`. |
| `app/services/archiver.py` | `Archiver`: оркестратор `/new` (см. `memory.md` §3.3). |
| `app/services/skills.py` | `SkillRegistry`: парсинг `_skills/`, `list_descriptions`, `get_body`. |
| `app/services/prompts.py` | `PromptLoader`: чтение `_prompts/`, подстановка плейсхолдеров. |
| `app/services/model_registry.py` | `UserSettingsRegistry`: per-user активная модель + system_prompt (in-memory). |
| `app/services/transcribe.py` | `Transcriber`: обёртка над faster-whisper для транскрипции голосовых сообщений. |
| `app/services/vision.py` | `Vision`: обёртка над OllamaClient.chat с поддержкой параметра `images`. |
| `app/services/ocr.py` | `OCR`: обёртка над pytesseract для распознавания текста с изображений. |
| `app/services/conversation_subscriber.py` | Подписчики EventBus для записи в ConversationStore. |
| `app/services/summarizer_subscriber.py` | Подписчик для in-session суммаризации. |
| `app/services/tmp_cleanup.py` | Подписчик для очистки tmp-изображений при /new. |
| `app/services/session_bootstrap.py` | Авто-подгрузка контекста из SemanticMemory при старте сессии. |
| `app/security/input_sanitizer.py` | `sanitize_user_input`: защита от prompt injection. |
| `app/security/file_id_mapper.py` | `FileIdMapper`: маскирование путей к файлам, персистентность через SQLite. |
| `app/security/response_sanitizer.py` | `sanitize_response`: фильтрация системной информации в ответах модели. |
| `app/users/repository.py` | `UserRepository`: хранилище пользователей с get_or_create, публикует UserCreated. |
| `app/adapters/telegram/handlers/commands.py` | Router с `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`. |
| `app/adapters/telegram/handlers/messages.py` | Router с обработчиком `F.text & ~F.text.startswith('/')` → `core.handle_user_task`, обработка файлов (Document, Voice, Photo). |
| `app/adapters/telegram/files.py` | `download_telegram_file`: скачивание файлов из Telegram с проверкой размера. |
| `app/adapters/telegram/handlers/errors.py` | `@router.errors()` — единая точка для необработанных ошибок. |
| `app/adapters/console/adapter.py` | REPL-цикл с теми же командами, что и Telegram-адаптер (без файловых операций). |
| `app/middlewares/logging_mw.py` | Логирование каждого апдейта (`user`, `chat`, `type`, `dur_ms`, `status`). |
| `app/utils/text.py` | `split_long_message` — разбивка длинных ответов LLM по границам строк/пробелов (Telegram limit 4096). |
| `tests/` | Зеркалирует `app/`, unit-тесты с моками. Сетевых вызовов нет; `sqlite-vec` — на `tmp_path`. |

## Принципы организации

- **Слои не протекают**: handler не знает про HTTP / sqlite, агентный цикл не знает про aiogram, tool не знает про LLM. Все зависимости — через DI (передача в конструктор / `ToolContext`).
- **Один tool — один файл.** `app/tools/<name>.py` для каждого инструмента.
- **Один skill — одна подпапка.** `_skills/<name>/SKILL.md`.
- **DI через aiogram `workflow_data`**: `dp["settings"]`, `dp["llm"]`, `dp["registry"]`, `dp["conversation"]`, `dp["summarizer"]`, `dp["memory"]`, `dp["archiver"]`, `dp["skills"]`, `dp["prompts"]`, `dp["tools"]`, `dp["executor"]`. Хендлеры получают их через параметры (aiogram 3 умеет инжектить по имени).
- **Тесты рядом с тем, что тестируют**: `tests/services/` зеркалит `app/services/`, `tests/tools/` — `app/tools/`, и т. д.
- **Адаптеры изолированы**: при добавлении web/MAX в `app/adapters/<channel>/` корневая структура не меняется, только подкаталог; единая точка входа — `core/orchestrator.py::handle_user_task`.

## Что должно попасть в `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Tests / tools
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# IDE
.idea/
.vscode/

# Logs
logs/
*.log

# Locally-built data (vector DB, runtime caches)
data/
*.db
*.db-journal
*.db-wal
*.db-shm

# Secrets
.env
.env.*
!.env.example
```
