# Инструкции по разработке

Этот документ описывает правила, которым должен следовать разработчик (и/или LLM-ассистент) при работе над проектом. Для общих поведенческих гайдлайнов LLM-агента (think before coding, simplicity, surgical changes, goal-driven) — `CLAUDE.md` в корне.

## 1. Git-дисциплина

- Основная ветка — `main`, рабочие ветки — `feature/<short-name>` (по одной на спринт).
- Коммиты — атомарные, сообщения **на русском**, в императиве, по [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat(handlers): добавить команду /new`
  - `fix(memory): обработать недоступность sqlite-vec при старте`
  - `test(tools): покрыть calculator случаем деления на ноль`
  - `docs(architecture): уточнить поток /new в §5`
  - `chore(plan): start task 01.2.3`
- `.gitignore` обязательно содержит: `.env`, `venv/`, `.venv/`, `__pycache__/`, `*.pyc`, `logs/`, `data/`, `*.db`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.idea/`, `.vscode/`. См. `project-structure.md` § «Что должно попасть в `.gitignore`».
- **Секреты никогда не коммитить.** Если токен / БД с приватными данными случайно попали — ротировать в @BotFather, удалить из истории (`git filter-repo`), удалить `.db`-файл.

## 2. Стиль кода

- Python 3.11+, type hints **обязательны** в сервис-слое и публичных функциях.
- Форматирование — `ruff format` (или `black`), длина строки 100.
- Импорты — `ruff` / `isort`-совместимо: stdlib → third-party → local.
- Имена: `snake_case` для функций/переменных, `PascalCase` для классов, `UPPER_CASE` для констант.
- Docstrings — краткие, на русском или английском, единообразно в рамках файла.
- Никаких `print` в продуктовом коде — только `logging`.

## 3. Async-дисциплина

- Любой I/O (HTTP, файлы в hot path, Telegram API, `sqlite-vec`) — только через `await`.
- Не использовать `requests`, `time.sleep`, блокирующие SDK. Только `httpx.AsyncClient`, `aiofiles` (если нужно), `ollama.AsyncClient`. Для синхронных библиотек (`sqlite3`, `ddgs`) — `asyncio.to_thread(...)`.
- Не создавать новый event loop внутри handlers / tools. Всё работает в loop'е, запущенном aiogram.
- Общие клиенты (HTTP, Ollama, SQLite-соединение) — создаются **один раз на приложение**, закрываются при shutdown.

## 4. Обработка ошибок

- Каждый handler / tool / агентный цикл либо сам ловит ожидаемые исключения (`LLMError`, `ToolError`, `asyncio.TimeoutError`), либо полагается на глобальный error handler в Dispatcher.
- Необработанных исключений быть не должно (см. NFR-3).
- Сообщения пользователю — человеческие, без stacktrace. Stacktrace — только в лог (`logger.exception(...)`).
- Иерархии исключений — в `app/services/llm.py` (`LLMError → LLMTimeout / LLMUnavailable / LLMBadResponse`) и `app/tools/errors.py` (`ToolError → ToolNotFound / ArgsValidationError`).

## 5. Логирование

- Конфиг один — `app/logging_config.py`.
- Каждый шаг агентного цикла логируется одной INFO-строкой (см. `agent-loop.md` §6).
- Каждый запрос к LLM — отдельной строкой (`model`, `len_in`, `len_out`, `dur_ms`, `status`).
- Каждый запуск tool — строкой из реестра (`tool=<name> dur_ms=<n> status=ok|error`).
- Ошибки — `logger.exception` или `logger.error(..., exc_info=True)`.
- Чувствительные данные (токен, сырые сообщения пользователей при `LOG_LLM_CONTEXT=false`) — никогда в логи.

## 6. Секреты и конфиг

- Все секреты и настройки — из `.env` через `pydantic-settings`.
- `.env` — в `.gitignore`, в репо — `.env.example` с описанием каждого поля.
- Не хардкодить токены, URL'ы, имена моделей, пути к БД в коде. Всё через `Settings`.

## 7. Тестирование

См. подробно `testing.md`. Минимум:

- `pytest` + `pytest-asyncio`.
- Unit-тесты для парсера JSON ответа модели (`tests/agents/test_protocol.py`).
- Unit-тесты для агентного цикла (мок LLM, мок tools).
- Unit-тесты для каждого tool (мок внешних зависимостей).
- Unit-тесты для `SemanticMemory` (с реальным `sqlite-vec` на `tmp_path`).
- Unit-тесты для handler'ов (мок `Executor` / `Archiver` / `OllamaClient`).
- `pytest` должен проходить локально одной командой без реального Telegram / Ollama / интернета.

### 7.1 Обязательное правило (тесты на новое поведение)

Новый или изменённый код в `app/` **не принимается без unit-теста на новое поведение**. Целевое покрытие из `testing.md` §5: пакет `app/` ≥ 70%, `app/services/` / `app/agents/` / `app/tools/` ≥ 85%.

Чисто-документационные задачи (правят только `_docs/`, `_board/`, `README.md`, `.env.example`, `_skills/`, `_prompts/`) от этого правила освобождены — в DoD таких задач явно ставится `n/a` напротив пункта про тесты.

### 7.2 Обязательное правило (зелёный pytest перед коммитом)

Перед каждым коммитом задачи прогнать `pytest -q` локально. Коммит идёт **только при зелёном результате**. Если тесты падают (даже не относящиеся к задаче) — сначала чинятся, и только потом фиксируются изменения. Это касается любых коммитов задачи, кроме `chore(plan): start/complete task ...` (они не меняют код).

## 8. Документация

- Документация ведётся **на русском** (как и сообщения коммитов).
- Технические идентификаторы (имена модулей, функций, переменных, env, путей) — латиницей, как в коде.
- Перед коммитом задачи, меняющей поведение, обновить соответствующий документ в `_docs/`. См. `process.md` §10.
- Перекрёстные ссылки — относительными путями (`./architecture.md` `_docs/agent-loop.md` и т. п.).
- Источник истины — код. При расхождении документ приводится в соответствие отдельным `docs(...)`-коммитом.

## 9. Процесс добавления фичи

1. Описать поведение в соответствующем документе (`requirements.md` / `commands.md` / `agent-loop.md` / `tools.md` / `memory.md` / `skills.md`).
2. При необходимости обновить `architecture.md` (новый компонент / поток).
3. Написать/обновить тест (красный).
4. Реализовать (зелёный).
5. Отрефакторить, прогнать линтер.
6. Обновить `README.md`, если появилась новая команда / параметр / зависимость.
7. **Прогнать `pytest -q` — все тесты зелёные.** Без этого шага коммит не делается (см. §7.2).
8. Коммит + push.

## 10. Что НЕЛЬЗЯ делать

- Использовать **облачные LLM** (OpenAI, Anthropic, Google и т. п.) — проект построен вокруг локальной LLM (`requirements.md` CON-2).
- Хранить **сырые сообщения** диалога в БД — нарушает CON-1. В архивную память пишутся только саммари.
- Заводить **другие БД**, кроме `sqlite-vec` — нарушает CON-3.
- Переходить на **webhook** в MVP — `requirements.md` CON-4.
- Возвращать ответ агента **вне JSON-схемы** из `agent-loop.md` §2 — это считается ошибкой.
- Коммитить `.env`, реальный токен, логи, `data/*.db`.
- Писать **синхронный I/O** в event loop'е (см. §3).
- **Удалять** ранее существовавший мёртвый код, не относящийся к задаче (см. `CLAUDE.md` §3).
- **Расширять scope** задачи без явного согласования (см. `CLAUDE.md` §2).

## 11. Локальный запуск (dev)

```bash
# 1) окружение
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) секреты
cp .env.example .env
# отредактировать .env — вписать TELEGRAM_BOT_TOKEN

# 3) Ollama
ollama serve &
ollama pull qwen3.5:4b
ollama pull nomic-embed-text

# 4) запуск бота
python -m app

# 5) тесты
pytest -q
```
