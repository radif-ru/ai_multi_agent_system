# ai_multi_agent_system

Telegram-бот, работающий как **AI-агент** на локальной LLM. Принимает задачу от пользователя, **выполняет цикл `thought → action → observation`** до получения финального ответа: думает, выбирает инструмент, наблюдает результат, повторяет. Ответ модели — строго в JSON-формате (`{"thought", "action", "args"}` либо `{"final_answer"}`).

Заложен под **мульти-агентную систему**: уже сейчас в архитектуре выделены роли Planner / Executor / Critic, но в первом MVP реализован только Executor (один агентный цикл). Будущие спринты добавят остальные роли и новые адаптеры (web-версия, мессенджер MAX) поверх той же доменной модели.

Построен на [`aiogram 3`](https://docs.aiogram.dev/) (long polling) + [`ollama`](https://ollama.com) (LLM + embeddings) + [`sqlite-vec`](https://github.com/asg017/sqlite-vec) (долгосрочная семантическая память) + `pydantic-settings` + `pytest`.

## Возможности

Реализовано в спринтах 01 (MVP Agent) и 02 (Память и файловые входы), состояние кода фиксируется в `_board/sprints/01-mvp-agent.md` и `_board/sprints/02-memory-and-files.md`.

- **Агентный цикл** `thought → action → observation` со строгим JSON-форматом, лимитом `AGENT_MAX_STEPS` и лимитом размера output’а — [`app/agents/executor.py`](./app/agents/executor.py), [`app/agents/protocol.py`](./app/agents/protocol.py).
- **Локальная LLM** через Ollama (`qwen3.5:4b` по умолчанию), клиент с `chat` и `embed` — [`app/services/llm.py`](./app/services/llm.py).
- **Tools (инструменты)**: `calculator`, `read_file`, `http_request`, `web_search` (DuckDuckGo `ddgs`), `memory_search`, `load_skill`, `read_document` — [`app/tools/`](./app/tools).
- **Telegram-интерфейс** на aiogram 3 (long polling), команды `/start`, `/help`, `/new`, `/reset`, `/models`, `/model`, `/prompt` + обработчик произвольного текста и файлов — [`app/adapters/telegram/handlers/`](./app/adapters/telegram/handlers).
- **Файловые входы**: документы (PDF/TXT/MD), голосовые сообщения (Voice/Audio), фотографии (Photo) — [`app/adapters/telegram/files.py`](./app/adapters/telegram/files.py), [`app/services/transcribe.py`](./app/services/transcribe.py), [`app/services/vision.py`](./app/services/vision.py).
- **Краткосрочная память** per-user (in-memory FIFO + in-session суммаризация + полный лог сессии) — [`app/services/conversation.py`](./app/services/conversation.py), [`app/services/summarizer.py`](./app/services/summarizer.py).
- **Долгосрочная семантическая память** на `sqlite-vec`: `/new` суммирует сессию, режет на чанки, пишет с embedding'ом в `data/memory.db`; поиск через `memory_search` — [`app/services/memory.py`](./app/services/memory.py), [`app/services/archiver.py`](./app/services/archiver.py).
- **Авто-подгрузка архива** при старте новой сессии через `SemanticMemory.search` — [`app/core/orchestrator.py`](./app/core/orchestrator.py).
- **Skills** из [`_skills/`](./_skills): markdown с `Description:` в первой строке; описания инжектятся в системный промпт, полное тело — через tool `load_skill` — [`app/services/skills.py`](./app/services/skills.py).
- **Prompts** (`_prompts/`): системный промпт агента и промпт суммаризации в markdown — [`app/services/prompts.py`](./app/services/prompts.py).
- **Настройки на пользователя** (выбранная модель, промпт) — [`app/services/model_registry.py`](./app/services/model_registry.py).
- **Логирование** через `RotatingFileHandler` + middleware на каждый update — [`app/logging_config.py`](./app/logging_config.py), [`app/middlewares/logging_mw.py`](./app/middlewares/logging_mw.py).
- **Сборка приложения** (DI, polling, graceful shutdown) — [`app/main.py`](./app/main.py), точка входа [`app/__main__.py`](./app/__main__.py).
- **Unit-тесты** через моки ([`tests/`](./tests)): без реального Telegram / Ollama / сети; `sqlite-vec` — на `tmp_path`.

## Требования

- **Python** 3.11+ (рекомендуется 3.12).
- **Ollama** (`https://ollama.com`) с предзагруженными моделями `qwen3.5:4b` и `nomic-embed-text`.
- **Telegram bot token** от [@BotFather](https://t.me/BotFather).
- ОС: Linux / WSL2 / macOS. Windows нативно — не приоритет.

## Установка

```bash
git clone <repo-url>
cd ai_multi_agent_system

python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## Настройка

1. Скопировать шаблон конфигурации и отредактировать секреты:

   ```bash
   cp .env.example .env
   # вписать TELEGRAM_BOT_TOKEN, при необходимости поменять модели/пути
   ```

2. Загрузить модели в Ollama:

   ```bash
   ollama pull qwen3.5:4b
   ollama pull nomic-embed-text
   ollama list   # убедиться, что обе модели доступны
   ```

3. Полный список переменных окружения — в `_docs/stack.md` §9 и в самом `.env.example` (поля прокомментированы).

## Запуск

```bash
ollama serve &              # если Ollama ещё не запущена
source .venv/bin/activate
python -m app
```

## Команды бота

| Команда            | Параметры       | Что делает                                                               |
|--------------------|-----------------|--------------------------------------------------------------------------|
| `/start`           | —               | Приветствие, краткая инструкция, список команд.                          |
| `/help`            | —               | Подробная справка.                                                       |
| `/new`             | —               | Архивирует текущую сессию (саммари → чанки → `sqlite-vec`), открывает новую. |
| `/reset`           | —               | Очищает текущую in-memory историю и per-user настройки. Архив **не трогает**. |
| `/models`          | —               | Список `OLLAMA_AVAILABLE_MODELS` с пометкой активной.                    |
| `/model <name>`    | имя модели      | Переключить активную LLM для пользователя.                               |
| `/prompt [<text>]` | текст \| пусто  | Задать системный промпт; без аргумента — сброс к default из `_prompts/`. |
| *произвольный текст* | —             | Запустить агентный цикл с этой задачей; вернуть финальный ответ.         |

Подробное поведение каждой команды — в `_docs/commands.md`.

## Структура проекта (целевая)

```
ai_multi_agent_system/
├── _docs/        # проектная документация (см. _docs/README.md)
├── _board/       # доска задач: спринты + процесс
├── _skills/      # markdown-скиллы (SKILL.md в каждой подпапке)
├── _prompts/     # системные промпты в markdown
├── app/          # код приложения (агент, tools, adapters)
├── tests/        # unit-тесты, зеркалят app/
├── data/         # runtime-данные: SQLite с sqlite-vec (в .gitignore)
└── logs/         # файлы логов (в .gitignore)
```

Полное дерево с пояснениями — `_docs/project-structure.md`.

## Тесты

```bash
pytest -q
```

Покрытие (если установлен `pytest-cov`):

```bash
pytest --cov=app --cov-report=term-missing
```

Тесты не делают сетевых вызовов — `aiogram.Bot`, `Message`, `ollama.AsyncClient`, `sqlite-vec` мокаются (см. `_docs/testing.md`).

## Документация

- 📘 [`_docs/README.md`](./_docs/README.md) — индекс проектной документации.
- 🏗️ [`_docs/architecture.md`](./_docs/architecture.md) — компоненты, агентный цикл, RAG, расширяемость.
- 🔁 [`_docs/agent-loop.md`](./_docs/agent-loop.md) — формат JSON ответа, шаги цикла, лимиты.
- 🧠 [`_docs/memory.md`](./_docs/memory.md) — краткосрочная и долгосрочная память.
- 🧰 [`_docs/tools.md`](./_docs/tools.md) — реестр инструментов и контракт нового tool.
- 🪄 [`_docs/skills.md`](./_docs/skills.md) — формат `_skills/<name>/SKILL.md`.
- 💬 [`_docs/commands.md`](./_docs/commands.md) — команды бота.
- 🛠️ [`_docs/instructions.md`](./_docs/instructions.md) — правила разработки (включая обязательные тесты перед коммитом).
- 📋 [`_board/README.md`](./_board/README.md) — процесс спринтов и задач.
- 📌 [`_docs/current-state.md`](./_docs/current-state.md) — фактическое состояние кода (читать перед правками).
- 🗺️ [`_docs/roadmap.md`](./_docs/roadmap.md) — этапы развития, в т.ч. multi-agent (Planner/Critic) и web/MAX-адаптеры.

## Ограничения и принципы

- Только **локальная LLM** через Ollama, никаких облачных API.
- Только **long polling**, без webhook (см. `_docs/architecture.md` §2).
- **In-memory** история текущей сессии, **долгосрочная** память — только саммари (не сырые сообщения), для приватности.
- Поддерживаются файловые входы: документы (PDF/TXT/MD), голосовые сообщения (Voice/Audio), фотографии (Photo) — через `faster-whisper` (опционально) и Ollama vision API (опционально).
- Документация и сообщения коммитов ведутся **на русском**, технические идентификаторы — латиницей.

## Известные дыры MVP (закрыты Спринтом 02)

После Спринта 01 (`_board/sprints/01-mvp-agent.md`) остались два видимых пользователю дефекта. Оба закрыты Спринтом 02 «Память и файловые входы»:

1. ~~**Каждое сообщение начинается «с чистого листа».**~~ ✅ Исправлено в Этапе 1 Спринта 02: `Executor.run` теперь принимает `history` и собирает контекст из `[system, history, user_goal]`. Авто-подгрузка архива при старте новой сессии (`SESSION_BOOTSTRAP_ENABLED`).
2. ~~**Бот не принимает файлы.**~~ ✅ Исправлено в Этапе 3 Спринта 02: реализованы handler'ы для Document (PDF/TXT/MD), Voice (faster-whisper), Photo (Ollama vision API).
