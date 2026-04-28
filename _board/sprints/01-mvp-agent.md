# Спринт 01. MVP Agent

- **Источник:** ТЗ пользователя; `_docs/mvp.md`; `_docs/roadmap.md` Этап 1.
- **Ветка:** `feature/mvp-agent` (создаётся при старте спринта от актуальной `main` после закрытия Спринта 00).
- **Открыт:** 2026-04-28
- **Закрыт:** —

## 1. Цель спринта

Реализовать минимально-полный AI-агент, удовлетворяющий ТЗ:

- Принимает задачу пользователя в Telegram (long polling).
- Решает её через цикл `thought → action → observation → ...`.
- LLM возвращает строго JSON одной из двух схем (`{thought, action, args}` / `{final_answer}`).
- Использует tools: `calculator`, `read_file`, `http_request`, `web_search`, `memory_search`, `load_skill`.
- Имеет краткосрочную (in-memory) и долгосрочную (sqlite-vec) память.
- Поддерживает команду `/new` для архивирования сессии в долгосрочную память.
- Поддерживает skills из `_skills/` и системный промпт из `_prompts/`.
- Покрыт unit-тестами (без сетевых вызовов).

Подробные критерии — в `_docs/mvp.md` §5.

## 2. Скоуп и non-goals

### В скоупе

- Конфигурация (`Settings`), логирование, LLM-клиент с `chat` и `embed`.
- Краткосрочная память (`ConversationStore`, `Summarizer`).
- Парсер JSON ответа модели (`AgentDecision`).
- Реестр и MVP-набор tools.
- Долгосрочная память на `sqlite-vec` (`SemanticMemory`, `Archiver`).
- `SkillRegistry`, `PromptLoader`.
- `Executor` (агентный цикл).
- `Core` (`handle_user_task`).
- Telegram-адаптер (handlers, middleware, errors).
- Тесты на каждый компонент.

### Вне скоупа

- Multi-agent (Planner, Critic) — `_docs/roadmap.md` Этап 4.
- Web / MAX адаптеры — Этап 5.
- Webhook — Этап 6.
- Файловые входы (фото, аудио, документы) — Этап 7.
- Стриминг ответа Ollama — Этап 3.
- Стриминг шагов агента в Telegram — Этап 2.
- Throttling middleware — Этап 9.
- Docker — Этап 10.
- CI — Этап 11.

## 3. Acceptance Criteria спринта

Один-в-один из `_docs/mvp.md` §5:

- [ ] `python -m app` стартует, в логе появляется `Bot started`.
- [ ] `/start` отвечает приветствием со списком команд.
- [ ] Агент решает калькуляторную задачу `(123 + 456) * 2 = 1158` (в логах виден цикл шагов).
- [ ] Агент решает файловую задачу (число строк в файле из `data/`).
- [ ] Агент решает поисковую задачу (использует `web_search` или `http_request`).
- [ ] `/new` пишет в `data/memory.db` хотя бы один чанк (проверяется тестом).
- [ ] `memory_search` в новой сессии находит прежнюю информацию.
- [ ] `/models`, `/model` работают.
- [ ] При остановленной Ollama бот не падает, отвечает понятным сообщением.
- [ ] Превышение `AGENT_MAX_STEPS` → корректный выход.
- [ ] Логи: файл создаётся, шаги цикла и LLM-вызовы пишутся.
- [ ] Секреты: реальный `.env` отсутствует в git.
- [ ] `pytest -q` зелёный, покрытие соответствует целям из `_docs/testing.md` §5.
- [ ] `README.md` обновлён.

## 4. Этап 1. Базовая инфраструктура (config, logging, LLM)

Без этого ничего не запустится.

### Задача 1.1. Конфигурация (`Settings`) + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/stack.md` §9; `_docs/architecture.md` §3.2.
- **Затрагиваемые файлы:** `app/config.py`, `tests/test_config.py`.

#### Описание

Реализовать `app/config.py::Settings(BaseSettings)` со всеми полями из `_docs/stack.md` §9, валидаторами из `_docs/architecture.md` §3.2.

#### Definition of Done

- [x] `Settings` загружает все поля из `.env`.
- [x] Валидаторы: `OLLAMA_DEFAULT_MODEL ∈ OLLAMA_AVAILABLE_MODELS`; `HISTORY_SUMMARY_THRESHOLD ≤ HISTORY_MAX_MESSAGES`, оба `> 0`; `EMBEDDING_DIMENSIONS > 0`; `AGENT_SYSTEM_PROMPT_PATH` существует.
- [x] `tests/test_config.py` покрывает позитивные и каждый негативный случай (см. `_docs/testing.md` §3.1).
- [x] `pytest -q` зелёный.
- [x] `git status` чист.

---

### Задача 1.2. Логирование (`setup_logging`) + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/stack.md` §8; `_docs/architecture.md` §3.3.
- **Затрагиваемые файлы:** `app/logging_config.py`, `tests/test_logging_config.py`.

#### Описание

`logging.config.dictConfig` с консольным и файловым (`RotatingFileHandler`) handler'ами. Каталог `LOG_FILE` создаётся автоматически.

#### Definition of Done

- [x] `setup_logging(settings)` корректно настраивает root-логгер.
- [x] Тест `test_setup_logging_creates_file_and_dir` (через `tmp_path`).
- [x] `pytest -q` зелёный.

---

### Задача 1.3. LLM-клиент (`OllamaClient`) + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/architecture.md` §3.4; `_docs/testing.md` §3.2.
- **Затрагиваемые файлы:** `app/services/llm.py`, `tests/services/test_llm_client.py`.

#### Описание

Реализовать `OllamaClient` с методами `chat(messages, model, temperature)`, `embed(text, model)`, `close()`. Иерархия исключений `LLMError → LLMTimeout/LLMUnavailable/LLMBadResponse`. Маппинг ошибок httpx/ollama. Метрики в INFO-лог.

#### Definition of Done

- [x] Все методы реализованы.
- [x] Каждый сценарий из `_docs/testing.md` §3.2 покрыт тестом.
- [x] `pytest -q` зелёный.

---

## 5. Этап 2. Память (краткосрочная + долгосрочная)

### Задача 2.1. `ConversationStore` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/memory.md` §2; `_docs/architecture.md` §3.5.
- **Затрагиваемые файлы:** `app/services/conversation.py`, `tests/services/test_conversation_store.py`.

#### Описание

In-memory история per-user, FIFO-обрезка, `conversation_id`, `replace_with_summary`, `clear`, `rotate_conversation_id`.

#### Definition of Done

- [x] Все методы из `_docs/memory.md` §2.2 реализованы.
- [x] Тесты на FIFO, `replace_with_summary`, изоляцию пользователей, `rotate_conversation_id`.
- [x] `get_history` возвращает копию (тест на мутацию).

---

### Задача 2.2. `Summarizer` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.3, Задача 2.1
- **Связанные документы:** `_docs/architecture.md` §3.5.
- **Затрагиваемые файлы:** `app/services/summarizer.py`, `tests/services/test_summarizer.py`.

#### Описание

Тонкая обёртка над `OllamaClient.chat` с системным промптом из `Settings.summarization_prompt`. Используется и для in-session порога, и для архивирования.

#### Definition of Done

- [x] `summarize(messages, model)` собирает payload и вызывает chat.
- [x] Падение `LLMError` пробрасывается (без глушения).
- [x] Тесты на успех и на ошибку.

---

### Задача 2.3. `SemanticMemory` (`sqlite-vec`) + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/memory.md` §3, §5; `_docs/testing.md` §3.7.
- **Затрагиваемые файлы:** `app/services/memory.py`, `tests/services/test_memory.py`.

#### Описание

Обёртка над `sqlite3` + `sqlite_vec.load`. Схема из `_docs/memory.md` §5 (`memory_chunks` + `memory_vec`). API: `init`, `insert(text, embedding, metadata)`, `search(embedding, top_k, scope_user_id)`. Реальный `sqlite-vec` на `tmp_path` в тестах.

#### Definition of Done

- [x] Схема создаётся идемпотентно.
- [x] `insert` пишет в обе таблицы с одинаковым rowid.
- [x] `search` фильтрует по `user_id`, сортирует по `distance`.
- [x] Тест с реальным `sqlite-vec` (или `pytest.skip`, если extension не загружается).

---

### Задача 2.4. `Archiver` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.2, Задача 2.3
- **Связанные документы:** `_docs/memory.md` §3.3; `_docs/commands.md` § `/new`.
- **Затрагиваемые файлы:** `app/services/archiver.py`, `tests/services/test_archiver.py`.

#### Описание

Оркестратор `/new`: суммаризация → чанкование → embedding каждого чанка → запись в `SemanticMemory`. Падение шагов не должно оставлять «осиротевших» строк.

#### Definition of Done

- [x] `archive(history, conversation_id, user_id)` реализован полностью.
- [x] Тесты на корректное чанкование, на падение Summarizer, на падение embed на 2-м чанке.

---

## 6. Этап 3. Tools и реестр

### Задача 3.1. `Tool`-протокол, `ToolError`, `ToolRegistry` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/tools.md` §2, §3; `_docs/testing.md` §3.5.
- **Затрагиваемые файлы:** `app/tools/base.py`, `app/tools/errors.py`, `app/tools/registry.py`, `tests/tools/test_registry.py`.

#### Описание

`Tool`-Protocol, `ToolContext`-Protocol, `ToolRegistry.execute(name, args, ctx)` с валидацией args по `args_schema`, логированием, усечением output до `MAX_TOOL_OUTPUT_CHARS`.

#### Definition of Done

- [x] Все методы реализованы, валидация args через лёгкий внутренний валидатор (object/required/типы).
- [x] Тесты на все ветки из `_docs/testing.md` §3.5.

---

### Задача 3.2. Tool `calculator` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/tools.md` §4.1.
- **Затрагиваемые файлы:** `app/tools/calculator.py`, `tests/tools/test_calculator.py`.

---

### Задача 3.3. Tool `read_file` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/tools.md` §4.2.
- **Затрагиваемые файлы:** `app/tools/read_file.py`, `tests/tools/test_read_file.py`.

---

### Задача 3.4. Tool `http_request` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/tools.md` §4.3.
- **Затрагиваемые файлы:** `app/tools/http_request.py`, `tests/tools/test_http_request.py`.

---

### Задача 3.5. Tool `web_search` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/tools.md` §4.4.
- **Затрагиваемые файлы:** `app/tools/web_search.py`, `tests/tools/test_web_search.py`.

---

### Задача 3.6. Tool `memory_search` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1, Задача 2.3
- **Связанные документы:** `_docs/tools.md` §4.5.
- **Затрагиваемые файлы:** `app/tools/memory_search.py`, `tests/tools/test_memory_search.py`.

---

### Задача 3.7. Tool `load_skill` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** XS
- **Зависит от:** Задача 3.1, Задача 4.1
- **Связанные документы:** `_docs/tools.md` §4.6; `_docs/skills.md` §4.
- **Затрагиваемые файлы:** `app/tools/load_skill.py`, `tests/tools/test_load_skill.py`.

---

## 7. Этап 4. Skills и Prompts

### Задача 4.1. `SkillRegistry` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/skills.md`; `_docs/testing.md` §3.9.
- **Затрагиваемые файлы:** `app/services/skills.py`, `tests/services/test_skills.py`.

#### Описание

Сканирование `_skills/`, парсинг первой строки `Description: ...`, методы `list_descriptions`, `get_body(name)`.

#### Definition of Done

- [x] Все случаи из `_docs/testing.md` §3.9 покрыты.
- [x] При SKILL.md без `Description:` — ясная ошибка при загрузке.

---

### Задача 4.2. `PromptLoader` + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/prompts.md`; `_docs/testing.md` §3.10.
- **Затрагиваемые файлы:** `app/services/prompts.py`, `tests/services/test_prompts.py`.

#### Описание

Чтение `_prompts/agent_system.md` и `_prompts/summarizer.md`; подстановка `{{TOOLS_DESCRIPTION}}` и `{{SKILLS_DESCRIPTION}}`.

---

## 8. Этап 5. Агентный цикл

### Задача 5.1. Парсер JSON ответа модели (`AgentDecision`) + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/agent-loop.md` §2; `_docs/testing.md` §3.3.
- **Затрагиваемые файлы:** `app/agents/protocol.py`, `tests/agents/test_protocol.py`.

#### Описание

Dataclass `AgentDecision(kind, thought, action, args, final_answer)`. Функция `parse_agent_response(text) -> AgentDecision`. Все ошибки → `LLMBadResponse`.

#### Definition of Done

- [x] Покрытие 100% по этому модулю.
- [x] Все случаи из `_docs/testing.md` §3.3 покрыты.

---

### Задача 5.2. `Executor` (агентный цикл) + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** L
- **Зависит от:** Задача 1.3, Задача 3.1, Задача 4.1, Задача 4.2, Задача 5.1
- **Связанные документы:** `_docs/agent-loop.md`; `_docs/architecture.md` §3.11; `_docs/testing.md` §3.4.
- **Затрагиваемые файлы:** `app/agents/executor.py`, `tests/agents/test_executor.py`.

#### Описание

Цикл `thought → action → observation`, лимит шагов, лимит размера ответа, логирование шагов, обработка `ToolError` как observation, обработка `LLMBadResponse` как обрыв цикла.

#### Definition of Done

- [x] Все случаи из `_docs/testing.md` §3.4 покрыты.
- [x] Логи шагов проверяются через `caplog`.

---

## 9. Этап 6. Core + Telegram-адаптер

### Задача 6.1. `UserSettingsRegistry` + тесты

- **Статус:** Progress
- **Приоритет:** high
- **Объём:** XS
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/architecture.md`; `_docs/commands.md` § `/model`, `/prompt`, `/reset`.
- **Затрагиваемые файлы:** `app/services/model_registry.py`, `tests/services/test_model_registry.py`.

---

### Задача 6.2. `core.handle_user_task` + smoke-тест

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 5.2
- **Связанные документы:** `_docs/architecture.md` §3.10.
- **Затрагиваемые файлы:** `app/core/orchestrator.py`, `tests/test_main.py` (smoke).

---

### Задача 6.3. Handlers команд (`/start`, `/help`, `/models`, `/model`, `/prompt`, `/reset`) + тесты

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 6.1
- **Связанные документы:** `_docs/commands.md`; `_docs/testing.md` §3.11.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/commands.py`, `tests/adapters/telegram/test_commands.py`.

---

### Задача 6.4. Handler `/new` + тесты

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 2.4, Задача 6.3
- **Связанные документы:** `_docs/commands.md` § `/new`; `_docs/memory.md` §3.3.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/commands.py` (расширение), `tests/adapters/telegram/test_commands.py` (расширение).

---

### Задача 6.5. Handler произвольного текста (`messages`) + тесты

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 6.2, Задача 6.3, Задача 2.2
- **Связанные документы:** `_docs/commands.md` § «Произвольный текст»; `_docs/testing.md` §3.11.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `tests/adapters/telegram/test_messages.py`.

---

### Задача 6.6. `LoggingMiddleware` + тесты

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Задача 1.2
- **Связанные документы:** `_docs/architecture.md` §3.12.
- **Затрагиваемые файлы:** `app/middlewares/logging_mw.py`, `tests/test_middleware_logging.py`.

---

### Задача 6.7. Глобальный error handler + тесты

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** XS
- **Зависит от:** Задача 6.5
- **Связанные документы:** `_docs/architecture.md` §6; `_docs/testing.md` §3.11.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/errors.py`, `tests/adapters/telegram/test_errors.py`.

---

### Задача 6.8. `app/main.py` (сборка приложения) + smoke-тест

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Все задачи Этапа 1–6
- **Связанные документы:** `_docs/architecture.md` §3.1; `_docs/testing.md` §3.11.
- **Затрагиваемые файлы:** `app/main.py`, `app/__main__.py`, `tests/test_main.py`.

#### Описание

Сборка всех зависимостей (`OllamaClient`, регистры, `Executor`, …), регистрация роутеров и middleware, регистрация команд BotFather, запуск polling, корректный shutdown в `finally`.

#### Definition of Done

- [ ] `python -c "import asyncio; from app.main import main; print(main)"` отрабатывает.
- [ ] Smoke-тест `tests/test_main.py::test_main_logs_bot_started_and_closes` зелёный.
- [ ] При остановленной Ollama — `python -m app` всё равно запускается (LLM-вызовы упадут только при первом запросе пользователя; это ожидаемое поведение).

---

## 10. Этап 7. Полировка и приёмка

### Задача 7.1. Утилита `split_long_message` + тесты

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/testing.md` §3.11.
- **Затрагиваемые файлы:** `app/utils/text.py`, `tests/test_utils_text.py`.

---

### Задача 7.2. Обновление README + чек-лист приёмки

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 6.8
- **Связанные документы:** `_docs/mvp.md` §5; `_board/progress.txt`.
- **Затрагиваемые файлы:** `README.md`, `_board/progress.txt`.

#### Описание

После прогона всех smoke-проверок — обновить корневой `README.md` (раздел «Возможности» с ссылками на реальные файлы), пройтись по чек-листу из `_board/progress.txt` и поставить отметки.

#### Definition of Done

- [ ] `_board/progress.txt` — все пункты `[+]` или с понятным `[~]`.
- [ ] `README.md` — соответствует фактическому коду.
- [ ] Тесты: n/a (документация).

---

## 11. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | `sqlite-vec` extension не загружается на хост-системе | Graceful degradation: `SemanticMemory.init()` ловит ошибку, помечает себя как «недоступна», `memory_search` возвращает `ToolError("long-term memory unavailable")`, `/new` отвечает «архив сейчас недоступен». Тест `tests/services/test_memory.py` помечается `pytest.skip`. |
| 2 | `qwen3.5:4b` плохо держит JSON-формат | В `_prompts/agent_system.md` явно требуем JSON и приводим примеры; при `LLMBadResponse` цикл прерывается с понятным сообщением. Если будет систематическая проблема — переключаемся на более крупную модель через `.env` (без правки кода). |
| 3 | Долгий цикл (10 шагов × ~30 сек на CPU) → пользователь думает, что бот завис | Индикатор «печатает…» уже идёт; стриминг шагов — Этап 2 roadmap. В этом спринте — фиксим только базовое UX. |
| 4 | Embedding-модель отсутствует в Ollama | При старте `Archiver` / `memory_search` ловим `LLMUnavailable`/`LLMBadResponse` → понятное сообщение пользователю. |
| 5 | DuckDuckGo блокирует частые запросы (rate-limit) | Ошибка → `ToolError("search unavailable")`, агент отвечает «не получилось найти». Throttling — Этап 9 roadmap. |
| 6 | Скоуп раздувается в multi-agent | Этот файл явно говорит: «вне скоупа Planner/Critic». Любое предложение «давай заодно сделаем» — записывается в `_docs/roadmap.md`, не реализуется здесь. |

## 12. Сводная таблица задач спринта

| #   | Задача                                          | Приоритет | Объём | Статус | Зависит от                                  |
|-----|--------------------------------------------------|:---------:|:-----:|:------:|----------------------------------------------|
| 1.1 | Конфигурация (`Settings`) + тесты                | high      | S     | Done   | —                                            |
| 1.2 | Логирование (`setup_logging`) + тесты            | high      | S     | Done   | 1.1                                          |
| 1.3 | LLM-клиент (`OllamaClient`) + тесты              | high      | M     | Done   | 1.1                                          |
| 2.1 | `ConversationStore` + тесты                      | high      | S     | Done   | 1.1                                          |
| 2.2 | `Summarizer` + тесты                             | high      | S     | Done   | 1.3, 2.1                                     |
| 2.3 | `SemanticMemory` (`sqlite-vec`) + тесты          | high      | M     | Done   | 1.1                                          |
| 2.4 | `Archiver` + тесты                               | high      | M     | Done   | 2.2, 2.3                                     |
| 3.1 | `Tool`-протокол, `ToolError`, `ToolRegistry`     | high      | M     | Done   | 1.1                                          |
| 3.2 | Tool `calculator` + тесты                        | high      | S     | Done   | 3.1                                          |
| 3.3 | Tool `read_file` + тесты                         | high      | S     | Done   | 3.1                                          |
| 3.4 | Tool `http_request` + тесты                      | high      | S     | Done   | 3.1                                          |
| 3.5 | Tool `web_search` + тесты                        | high      | S     | Done   | 3.1                                          |
| 3.6 | Tool `memory_search` + тесты                     | high      | S     | Done   | 3.1, 2.3                                     |
| 3.7 | Tool `load_skill` + тесты                        | high      | XS    | Done   | 3.1, 4.1                                     |
| 4.1 | `SkillRegistry` + тесты                          | high      | S     | Done   | 1.1                                          |
| 4.2 | `PromptLoader` + тесты                           | high      | S     | Done   | 1.1                                          |
| 5.1 | Парсер JSON ответа модели + тесты                | high      | S     | Done   | —                                            |
| 5.2 | `Executor` (агентный цикл) + тесты               | high      | L     | Done   | 1.3, 3.1, 4.1, 4.2, 5.1                       |
| 6.1 | `UserSettingsRegistry` + тесты                   | high      | XS    | Progress | 1.1                                        |
| 6.2 | `core.handle_user_task` + smoke-тест             | high      | S     | ToDo   | 5.2                                          |
| 6.3 | Handlers команд + тесты                          | high      | M     | ToDo   | 6.1                                          |
| 6.4 | Handler `/new` + тесты                           | high      | S     | ToDo   | 2.4, 6.3                                     |
| 6.5 | Handler произвольного текста + тесты             | high      | M     | ToDo   | 6.2, 6.3, 2.2                                |
| 6.6 | `LoggingMiddleware` + тесты                      | medium    | XS    | ToDo   | 1.2                                          |
| 6.7 | Глобальный error handler + тесты                 | high      | XS    | ToDo   | 6.5                                          |
| 6.8 | `app/main.py` (сборка) + smoke-тест              | high      | M     | ToDo   | все задачи Этапов 1–6                         |
| 7.1 | `split_long_message` + тесты                     | medium    | XS    | ToDo   | —                                            |
| 7.2 | Обновление README + чек-лист приёмки             | high      | S     | ToDo   | 6.8                                          |

## 13. История изменений спринта

- **2026-04-28** — спринт открыт, ветка `feature/mvp-agent` создана от `main` (Спринт 00 закрыт коммитом `c54b0c2`).
- **2026-04-28** — закрыта задача 1.1 (`Settings` + тесты): `app/config.py`, `tests/test_config.py` (9 тестов). Коммит `40977a1`.
- **2026-04-28** — закрыта задача 1.2 (`setup_logging` + тест): `app/logging_config.py`, `tests/test_logging_config.py`. Коммит `1b24c2e`.
- **2026-04-28** — закрыта задача 1.3 (`OllamaClient` + тесты): `app/services/llm.py`, `tests/services/test_llm_client.py` (13 тестов). Коммит `1997316`. Этап 1 завершён.
- **2026-04-28** — закрыта задача 2.1 (`ConversationStore` + тесты): `app/services/conversation.py`, `tests/services/test_conversation_store.py` (9 тестов).
- **2026-04-28** — закрыта задача 2.2 (`Summarizer` + тесты): `app/services/summarizer.py`, `tests/services/test_summarizer.py` (2 теста).
- **2026-04-28** — закрыта задача 2.3 (`SemanticMemory` + тесты): `app/services/memory.py`, `tests/services/test_memory.py` (6 тестов, реальный `sqlite-vec`).
- **2026-04-28** — закрыта задача 2.4 (`Archiver` + тесты): `app/services/archiver.py`, `tests/services/test_archiver.py` (8 тестов). Этап 2 завершён.
- **2026-04-28** — закрыты задачи 3.1–3.7 (Этап 3, tools и реестр): `app/tools/{base,errors,registry,calculator,read_file,http_request,web_search,memory_search,load_skill}.py` + 7 тест-модулей в `tests/tools/` (42 теста, всего 89 зелёных). Задача 3.7 опирается на контракт `ctx.skills.get_body(name)`; реальный `SkillRegistry` будет добавлен задачей 4.1, на тестах load_skill используется фейк. Этап 3 завершён.
- **2026-04-28** — закрыта задача 4.1 (`SkillRegistry` + тесты): `app/services/skills.py`, `tests/services/test_skills.py` (7 тестов).
- **2026-04-28** — закрыта задача 4.2 (`PromptLoader` + тесты): `app/services/prompts.py`, `tests/services/test_prompts.py` (7 тестов). Этап 4 завершён.
- **2026-04-28** — закрыта задача 5.1 (`AgentDecision` + парсер + тесты): `app/agents/protocol.py`, `tests/agents/test_protocol.py` (15 тестов).
- **2026-04-28** — закрыта задача 5.2 (`Executor` + тесты): `app/agents/executor.py`, `tests/agents/test_executor.py` (10 тестов). Этап 5 завершён.
