# Текущее состояние проекта

Документ фиксирует **фактическое состояние** кода `app/` на момент написания: что работает (§1), известные баги/легаси (§2), архитектурные нюансы (§3), что точно не сломано (§4), история закрытий багов (§6). **При расхождении с кодом приоритет у кода**, документ должен быть подправлен следующим коммитом.

Читать обязательно перед любыми правками.

**Роль документа:**

- **Не дублирует** `roadmap.md` (там — план будущих этапов) и `_board/plan.md` (там — индекс активных/закрытых спринтов).
- **Когда правится** — см. `_board/process.md` §8.2.

## 1. Что работает

> На момент закрытия Спринта 04 (События и пользователи) реализованы все задачи спринта: модуль Users с UserRepository, событийная шина EventBus с событиями UserCreated, MessageReceived, ResponseGenerated, ConversationArchived, подписчики для записи в ConversationStore, in-session суммаризации и очистки tmp-изображений. Также сохранены все задачи Этапов 1–5 Спринта 02 и Этапа 4 Спринта 03: агентный цикл, память, файловые входы (Document, Voice, Photo), авто-подгрузка архива, полное архивирование сессии, изоляция файлов по пользователям, сохранение контекста файлов для reply, инструмент weather, консольный адаптер.

Шаблон записи (для будущих спринтов):

```markdown
- **<Подсистема>** — `app/<path>.py` (что именно умеет, ссылки на основные методы / классы).
```

### 1.1 Агентный цикл

- **Executor** — `app/agents/executor.py` реализует цикл `thought → action → observation → final_answer` с лимитом шагов и обработкой ошибок LLM. Автоматическая суммаризация контекста: если размер контекста превышает `AGENT_MAX_CONTEXT_CHARS` (default 8000), история автоматически суммаризируется через `Summarizer` перед отправкой в LLM, что предотвращает пустые ответы при больших контекстах.
- **Protocol** — `app/agents/protocol.py` парсит JSON-ответы модели (с толерантностью к markdown-fence и к некорректному формату `action: "final_answer"`).

### 1.2 Память

- **ConversationStore** — `app/services/conversation.py` хранит in-memory историю, полный лог сессии (`_session_log`) и контекст файлов (`_file_contexts`) для reply. Поддерживает in-session compaction для LLM-контекста и сохраняет полный лог для `/new`. Контекст файлов сохраняется по ключу `(user_id, message_id, file_type)` и используется при reply на документы, голосовые и фотографии.
- **SemanticMemory** — `app/services/memory.py` — долгосрочная память на `sqlite-vec` для поиска по семантическому сходству.
- **Archiver** — `app/services/archiver.py` — оркестратор архивации сессии при `/new` (суммаризация → чанки → embedding → запись в `sqlite-vec`).
- **Summarizer** — `app/services/summarizer.py` — суммаризация истории (in-session и при архивировании), поддерживает map-reduce для длинных логов.

### 1.3 Файлы

- **download_telegram_file** — `app/adapters/telegram/files.py` — async-утилита для скачивания файлов из Telegram с проверкой размера (`TELEGRAM_MAX_FILE_MB`, default 20). Файлы сохраняются в отдельные каталоги `data/tmp/{user_id}/` для изоляции по пользователям.
- **Handler Document** — `app/adapters/telegram/handlers/messages.py` — обрабатывает `Document` сообщения (PDF/TXT/MD). Скачивает файл, формирует обогащённый goal, сохраняет контекст для reply, передаёт в агентный цикл. Файл не удаляется сразу — живёт до `/new` или TTL cleanup.
- **Handler Voice** — `app/adapters/telegram/handlers/messages.py` — обрабатывает `Voice`/`Audio` сообщения. Скачивает файл, транскрибирует через `Transcriber` (faster-whisper), сохраняет контекст для reply, передаёт распознанный текст в агентный цикл. Файл не удаляется сразу — живёт до `/new` или TTL cleanup.
- **Handler Photo** — `app/adapters/telegram/handlers/messages.py` — обрабатывает `Photo` сообщения. Скачивает файл, описывает через `Vision` (Ollama vision API), передаёт описание в агентный цикл. Файл не удаляется сразу — живёт до `/new` или TTL cleanup.
- **Transcriber** — `app/services/transcribe.py` — обёртка над `faster-whisper` для транскрипции речи. Опциональная зависимость.
- **Vision** — `app/services/vision.py` — обёртка над `OllamaClient.chat` с поддержкой параметра `images` для описания изображений.
- **ReadDocumentTool** — `app/tools/read_document.py` — tool для чтения документов из временной директории (PDF/TXT/MD/JPG/PNG). Защита от path traversal, усечение вывода. OCR делегируется сервису `app/services/ocr.py` (pytesseract). Дисковый кеш `.ocr.txt` убран (задача 06.3-bis.4) — результат OCR попадает в `dialog_journal.content` через goal. Поддержка кириллицы через `tesseract-ocr-rus`. Установка: `sudo apt-get install tesseract-ocr tesseract-ocr-rus`.
- **DescribeImageTool** — `app/tools/describe_image.py` — tool для повторного описания изображений по пути к файлу. Используется для уточнения деталей после первичного описания.
- **OcrImageTool** — `app/tools/ocr_image.py` — tool для распознавания текста с одиночных изображений через OCR. Используется для точной транскрипции текста (сканы документов, чеки, таблицы). OCR делегируется сервису `app/services/ocr.py`. Дисковый кеш `.ocr.txt` убран (задача 06.3-bis.4). Обрезка вывода до 8000 символов.
- **WeatherTool** — `app/tools/weather.py` — tool для получения погоды через wttr.in с fallback на WebSearchTool при недоступности сервиса.

### 1.4 Адаптеры

- **Telegram-адаптер** — `app/adapters/telegram/handlers/`:
  - **Commands** — `app/adapters/telegram/handlers/commands.py` — команды `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`.
  - **Messages** — `app/adapters/telegram/handlers/messages.py` — обработчик текста и файлов, вызов `core.handle_user_task`, поддержка reply на файлы (фото, документы, голосовые).
  - **Errors** — `app/adapters/telegram/handlers/errors.py` — глобальный error handler.
- **Консольный адаптер** — `app/adapters/console/adapter.py` — REPL-цикл с теми же командами, что и Telegram-адаптер (кроме файловых операций). Точка входа — `app/console_main.py`. См. `_docs/console-adapter.md`.

### 1.5 Пользователи и события

- **UserRepository** — `app/users/repository.py` — хранилище пользователей с методом `get_or_create(channel, external_id, display_name)`. Публикует событие `UserCreated` при создании нового пользователя. Интегрирован в точки входа (main.py, console_main.py) и хендлеры.
- **EventBus** — `app/core/events.py` — событийная шина для pub/sub между компонентами. Поддерживает регистрацию подписчиков и публикацию событий с гарантией порядка вызова (FIFO регистрации).
- **События спринта 04:**
  - `UserCreated` — публикуется при создании нового пользователя.
  - `MessageReceived` — публикуется хендлерами при получении сообщения пользователя. Подписчики: conversation_subscriber.on_message_received (запись в ConversationStore).
  - `ResponseGenerated` — публикуется хендлерами после генерации ответа LLM. Подписчики: conversation_subscriber.on_response_generated (запись в ConversationStore), summarizer_subscriber.on_response_generated_summarize (in-session суммаризация).
  - `ConversationArchived` — публикуется Archiver при успешном архивировании сессии. Подписчики: on_conversation_archived_cleanup (очистка tmp-изображений).
- **Подписчики:**
  - `conversation_subscriber.py` — подписчики on_message_received и on_response_generated для записи в ConversationStore.
  - `summarizer_subscriber.py` — подписчик on_response_generated_summarize для in-session суммаризации.
  - `tmp_cleanup.py` — подписчик on_conversation_archived_cleanup для очистки временных изображений.

### 1.6 Безопасность

- **InputSanitizer** — `app/security/input_sanitizer.py` — функция `sanitize_user_input` для защиты от prompt injection. Детектирует подозрительные паттерны (ignore instructions, repeat system prompt и т.д.) и возвращает очищенный текст или текст с предупреждением. Интегрирован в Telegram-хендлеры и консольный адаптер перед вызовом `core.handle_user_task`.
- **FileIdMapper** — `app/security/file_id_mapper.py` — класс для маскирования путей к файлам во избежание data leakage. Генерирует временные ID для файлов и умеет восстанавливать путь по ID. Использует общую таблицу `file_contexts` из ConversationStore для персистентности между перезапусками агента. Интегрирован в хендлеры файлов и tools (read_file, read_document).
- **ResponseSanitizer** — `app/security/response_sanitizer.py` — функция `sanitize_response` для фильтрации системной информации в ответах модели. Маскирует пути к файлам, конфигурационные ключи и фрагменты системного промпта. Интегрирован в executor для фильтрации `final_answer` перед возвращением пользователю.
- **Защита tools** — allowlist для опасных tools (http_request, read_file, read_document) в конфигурации и дополнительная валидация параметров (запрет на системные пути, path traversal).

### 1.7 Журнал диалога и observability (Спринт 06)

- **DialogJournal** — `app/services/dialog_journal.py` — append-only журнал текстовых и файловых сообщений (`MessageReceived`/`ResponseGenerated`) в той же `data/memory.db` (таблица `dialog_journal`, индекс `ix_journal_message` по `message_id`). API: `init/append/pending_conversations/read_conversation/mark_archived`. Подписчики — `app/services/dialog_journal_subscriber.py` (DI в `app/main.py` и `app/console_main.py`); ошибки журнала не валят основной поток. Журнал — единый источник истины для контекста файлов: `ConversationStore.get_file_context` и `FileIdMapper` читают `content`/`file_id`/`file_path` из `dialog_journal` по `(user_id, message_id)`. `data/file_contexts.db` сохранён только для одноразовой миграции (`app/services/file_contexts_migration.py`).
- **Автоматическое восстановление при старте** — `app/services/journal_recovery.py::recover_pending_journals` запускается в `asyncio.create_task` параллельно с polling и архивирует «зависшие» сессии из `dialog_journal`, для которых процесс не успел вызвать `Archiver.archive(...)`. После успешной архивации `cmd_new` помечает строки журнала через `mark_archived(...)`. См. `_docs/memory.md` §4.
- **Структурное JSON-логирование** — `app/core/logging_config.py::JsonFormatter` + `ContextFilter`. Каждая запись содержит `trace_id` и `user_id` из `contextvars` (`app/utils/tracing.py` — `new_trace_id/bind_trace_id/get_trace_id/reset_trace_id`); изоляция между `asyncio.Task` сохраняется. `LoggingMiddleware` (`app/middlewares/logging_mw.py`) и `ConsoleAdapter.run` биндят `trace_id`/`user_id` на каждый Telegram-event / команду и сбрасывают их в `finally`. На границах внешних вызовов пишутся структурные `external.call`/`external.ok`/`external.fail` с полями `service`/`duration_ms`/`status` (`app/services/llm.py`, `transcribe.py`, `vision.py`, `ocr.py`, `app/tools/http_request.py`, `web_search.py`); секреты маскируются через `app/utils/secrets.py::mask_secrets`. См. `_docs/observability.md` §1–§4.
- **Error tracking через GlitchTip / Sentry** — `app/observability/__init__.py::setup_sentry` (off-by-default: при пустом `SENTRY_DSN` ничего не инициализируется). `_before_send` подмешивает `trace_id`/`user_id` в `tags`/`extra`/`user`. Self-hosted GlitchTip разворачивается через `docker-compose.observability.yml` (postgres + redis + web/worker/migrate). См. `_docs/observability.md` §5.
- **CI (GitHub Actions)** — `.github/workflows/test.yml` прогоняет `flake8 app tests` и `pytest -q` на каждый push/PR (Python 3.14, ubuntu-latest, кеш pip по `requirements.txt`, без матрицы и секретов). Бейдж в шапке `README.md`. См. `_docs/instructions.md` §8.4.

### 1.8 Multi-agent (Спринт 07)

- **PlannerAgent** — `app/agents/planner.py` — одиночный LLM-вызов, превращает задачу в линейный `Plan` (1–6 шагов). При любой ошибке LLM/парсера возвращает fallback `Plan(steps=[PlanStep(1, task)])` (лог `planner.fallback`).
- **CriticAgent** — `app/agents/critic.py` — одиночный LLM-вызов, возвращает `CriticVerdict("PASS"|"REVISE", feedback)`. Fail-open: при любой ошибке возвращает `PASS` (лог `critic.fallback`).
- **Протоколы** — `app/agents/protocol.py`: `Plan`/`PlanStep`/`CriticVerdict` + парсеры `parse_planner_response`/`parse_critic_response` (толерантны к markdown-fence; константы `PLAN_MIN_STEPS=1`, `PLAN_MAX_STEPS=6`, `PLAN_STEP_DESCRIPTION_MAX_CHARS=200`).
- **Оркестрация** — `app/core/orchestrator.py::handle_user_task` поддерживает три режима: `OFF` (Executor напрямую), `NORMAL` (Planner → Executor → Critic, один проход), `DEEP` (Critic итерируется до `AGENT_REFLECTION_MAX_ITERATIONS`). Контракт `handle_user_task(text, user_id, chat_id)` стабилен для адаптеров; режим даунгрейдится в `OFF`, если `planner` или `critic` не переданы в DI.
- **Конфиг** — `Settings.agent_reflection_mode` (`OFF`/`NORMAL`/`DEEP`, default `OFF`) и `Settings.agent_reflection_max_iterations` (default `2`); per-user override — `UserSettingsRegistry.get_reflection_mode(user_id)`.
- **Команда `/mode`** — `app/commands/registry.py::cmd_mode`, доступна в Telegram и console; без аргументов показывает текущий режим, с `off|normal|deep` — выставляет per-user override.
- **Промпты** — `app/prompts/planner.md` (плейсхолдер `{{TASK}}`), `app/prompts/critic.md` (`{{TASK}}`/`{{PLAN}}`/`{{DRAFT}}`); рендер через `PromptLoader.render_planner` / `render_critic`.
- **Тесты** — `tests/agents/test_planner.py`, `tests/agents/test_critic.py`, `tests/core/test_orchestrator.py` (ветки OFF / NORMAL-PASS / NORMAL-REVISE / DEEP-лимит / DEEP-PASS-на-2 / per-user override / planner-fallback / critic-fail-open), `tests/test_multi_agent_e2e.py` (полный цикл DEEP с мок-LLM).
- **Документ** — `_docs/multi-agent.md` (роли, JSON-протоколы, поток, fallback'ы, логирование).

## 2. Известные проблемы и легаси

> Пусто на момент закрытия Спринта 00. Записи появляются по мере обнаружения нюансов в Спринтах 01+.

### 2.1 Потеря ранней истории при `/new` (исправлено в спринте 02, Этап 4)

**Статус:** ✅ Исправлено.

**Решение:** введён параллельный append-only `_session_log` в `ConversationStore`, `cmd_new` архивирует полный лог через `get_session_log()`, in-session compaction остаётся только для `_messages` (LLM-контекст). См. спринт 02 Этап 4 (`_board/sprints/02-memory-and-files.md`).

Шаблон записи:

```markdown
### 2.X Краткое название

**Файл:** `app/...py:строка`. **Серьёзность:** низкая | средняя | высокая.

Описание... Минимальное воспроизведение, если возможно...

**Рекомендация:** что делать. См. `roadmap.md`, если запланировано.
```

## 3. Архитектурные нюансы (не баги, но знать обязательно)

> Заполняется по мере реализации. На момент Спринта 00 — только проектные принципы, см. `architecture.md` §2.

Кандидаты, которые попадут сюда после Спринта 01 (опережающие заметки, чтобы не забыть зафиксировать):

- **In-memory per-user состояние, без персистентности на уровне сессии**: текущая модель, системный промпт **и** in-memory история диалога живут только в памяти процесса (см. `requirements.md` §FR-21, §CON-1, §ASM-4). Долгосрочная память (sqlite-vec) — это **только саммари**, не сырая история.
- **Контекст агента собирается на каждый шаг цикла**: `[system] + observations + ...`. См. `agent-loop.md` §4.
- **Оценка размера контекста** — грубая: `estimate_tokens = max(1, len(text) // 4)`. Используется только для логирования, не для ограничения запроса.
- **`/new` не очищает архив** — только пополняет его. Очистка архива — внешняя процедура (удаление `.db`-файла).
- **`/reset` не трогает архив** — только in-memory. Это контракт: «сбросить настройки» ≠ «забыть историю навсегда».
- **Ответ модели в цикле — строго JSON**, ничего другого; иначе `LLMBadResponse` (см. `agent-loop.md` §2). Это касается **только** Executor; вне цикла (например, при суммаризации) ответ — обычный текст.
- **Один общий `OllamaClient`** на всё приложение (создаётся в `main.py`, закрывается в `finally`). Не плодим клиенты в handler'ах / tools.
- **Один общий `SemanticMemory`** на всё приложение (одно SQLite-соединение с загруженным `sqlite-vec`).
- **Очерёдность роутеров** в `main.py`: `commands.router` → `messages.router` → `errors.router`. Команды должны идти раньше, чтобы текст вида `/start ...` не попал в обработчик произвольного текста.
- **Обработка длинных ответов**: handler `messages` сам режет ответ через `split_long_message`. Telegram обрежет всё, что > 4096, отдельной ошибкой `BadRequest` — это исключено резкой на стороне бота.
- **`parse_mode=ParseMode.HTML`** установлен по умолчанию (`DefaultBotProperties` в `main.py`). Все хендлеры должны экранировать пользовательский ввод (`html.escape`) перед вставкой.
- **Автоматическая суммаризация контекста**: Executor проверяет размер контекста перед отправкой в LLM. Если превышает `AGENT_MAX_CONTEXT_CHARS` (default 8000), история суммаризируется через `Summarizer` для предотвращения пустых ответов при больших контекстах (например, при обработке PDF с OCR текстом).
- **Порядок подписчиков EventBus**: подписчики вызываются последовательно в порядке регистрации (FIFO). Для события `ResponseGenerated` важно, чтобы `conversation_subscriber.on_response_generated` регистрировался первым, чтобы к моменту суммаризации ответ уже был записан в ConversationStore. Это гарантируется порядком регистрации в точках входа (main.py, console_main.py).
- **Top-level логирование необработанных исключений** (`app/main.py::run`, `app/console_main.py::run`, спринт 08 задача 6.1): обёртки оборачивают `asyncio.run(main())` в `try/except`. `KeyboardInterrupt` пробрасывается без лога (штатное завершение polling). Любое другое `BaseException` логируется через `logger.exception("необработанное исключение на верхнем уровне")` и пробрасывается дальше, чтобы Sentry/GlitchTip (через `LoggingIntegration` в `setup_sentry`) подхватил traceback. Дополнительный `sys.excepthook` не ставится сознательно.
- **Multi-agent fail-open / graceful degradation** (`app/core/orchestrator.py`, см. `multi-agent.md` §4): любые ошибки Planner/Critic не валят запрос пользователя. `Planner` бросил → Executor запускается на исходном `text` (лог `orchestrator.planner_fallback`). `Planner` вернул мусор → внутри `PlannerAgent` фолбэчится в `Plan(steps=[PlanStep(1, task)])` (лог `planner.fallback`). `Critic` бросил → возврат текущего draft (лог `orchestrator.critic_error`). `Critic` вернул мусор → fail-open `PASS` (лог `critic.fallback`). Re-run Executor бросил → возврат предыдущего draft. Контракт `handle_user_task(text, user_id, chat_id)` остаётся стабильным.

## 4. Что точно не сломано

> Будет заполнено после Спринта 01 (когда появится код, чтобы было о чём писать).

Чтобы не паниковать без причины, в этой секции фиксируется **то, что протестировано и работает заведомо**: грамотный shutdown клиентов, глобальный error handler, отсутствие сетевых вызовов в тестах, корректная сборка `main()` и т. д.

## 5. Как добавлять новые записи

При обнаружении проблемы:

1. Найти подходящую секцию (§2 — баги/легаси, §3 — нюансы).
2. Создать подсекцию по шаблону из §2.
3. Если решение запланировано — добавить запись в `_docs/roadmap.md`.
4. Если решение не запланировано — оставить «требует решения, кандидат на отдельную задачу».
5. Если запись описывает планируемое улучшение (а не нюанс текущего кода) — место для неё `_docs/roadmap.md`, а не §2 этого документа.

## 6. История закрытий

(Для будущих записей: когда баг исправлен — переносим запись сюда с указанием SHA коммита и даты.)

> Пусто на момент закрытия Спринта 00.

### 6.1 Парсер ответа агента не снимает markdown-fence (исправлено в спринте 02, Этап 5)

**Дата:** 2026-04-29. **SHA:** 53474b1971588dc72922cb71663a002548c2a6f9.

**Исходная проблема:** `parse_agent_response` в `app/agents/protocol.py` делал `json.loads(text)` без предобработки, а `qwen3.5:4b` оборачивала JSON в markdown-fence (```json ... ```). Это приводило к `LLMBadResponse` и сообщению пользователю «Модель ответила в неожиданном формате».

**Решение:** добавлена функция `_strip_code_fence(text)`, которая снимает fence-обёртку перед парсингом. Парсер теперь толерантен к ```json ... ``` и ``` ... ```. В системном промпте `app/prompts/agent_system.md` ужесточено требование о голом JSON без обёртки. В `_docs/agent-loop.md` §2.3 зафиксирована толерантность парсера.

### 6.2 LLM использует final_answer как действие (исправлено в спринте 03, задача 4.11)

**Дата:** 2026-05-04. **SHA:** 377206a.

**Исходная проблема:** LLM иногда возвращает некорректный формат `{"action": "final_answer", "args": {}}` вместо правильного `{"final_answer": "..."}`. Это приводило к ошибкам в парсере.

**Решение:** добавлена обработка случая `action == "final_answer"` в `_parse_action` в `app/agents/protocol.py` с преобразованием в правильный формат `AgentDecision(kind="final", final_answer=thought)`. В системном промпте `app/prompts/agent_system.md` добавлено явное предупреждение, что `final_answer` НЕ инструмент и его нельзя использовать как значение поля `action`.

### 6.3 Secure-by-default `dangerous_tools_allowlist` (закрыто в спринте 08, задача 1.1)

**Дата:** 2026-05-21.

**Исходная проблема:** в спринте 05 (задача 6.1) сознательно зафиксировано, что по умолчанию `dangerous_tools_allowlist` пустой и опасные tools (`http_request`, `read_file`) разрешены «для MVP». Документация в `_docs/security.md` §4.1 повторяла это утверждение. По факту код `app/tools/registry.py::execute` уже трактовал пустой allowlist как **запрет** (исправлено ранее без записи в документацию), но не логировал отказ как `WARNING` и `.env.example` не содержал подсказки.

**Решение:** зафиксирован контракт «secure by default» — пустой `DANGEROUS_TOOLS_ALLOWLIST` означает запрет всех опасных tools. В `ToolRegistry.execute` добавлен `WARNING`-лог с указанием tool и причины (`not_in_allowlist`). В `app/main.py::main` и `app/console_main.py::main` добавлена `INFO`-подсказка при пустом allowlist с готовой строкой для миграции. В `.env.example` добавлен закомментированный пример. Документация `_docs/security.md` §4.1 переписана.

**Миграция для существующих установок:** если опасные tools нужны — добавить в `.env`:
```
DANGEROUS_TOOLS_ALLOWLIST=http_request,read_file
```
