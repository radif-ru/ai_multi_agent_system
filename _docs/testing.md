# Стратегия тестирования

## 1. Цели

- Гарантировать соответствие требованиям из `requirements.md` (столбец «способ верификации» в §6).
- Ловить регрессии при доработках, особенно при перестройке агентного цикла.
- Проверять обработку ошибок LLM-слоя, tool-слоя и memory-слоя.
- Выполняться быстро (< 10 сек на MVP) и без внешних зависимостей (без реального Telegram, без реальной Ollama, без интернета).

## 2. Инструменты

- **`pytest`** — раннер.
- **`pytest-asyncio`** — поддержка `async def test_...`.
- **`pytest-mock`** — фикстура `mocker`.
- Опционально: **`pytest-cov`** для покрытия.

Конфиг (в `pyproject.toml`):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q"
```

## 3. Категории тестов

### 3.1 Unit — конфигурация (`tests/test_config.py`)

- `Settings` корректно читает `.env`-подобный ввод (через `_env_file` или `monkeypatch.setenv`).
- Отсутствие обязательного поля (`TELEGRAM_BOT_TOKEN`) → `ValidationError`.
- `OLLAMA_AVAILABLE_MODELS` парсится как список из CSV.
- `OLLAMA_DEFAULT_MODEL not in OLLAMA_AVAILABLE_MODELS` → `ValidationError`.
- `HISTORY_SUMMARY_THRESHOLD > HISTORY_MAX_MESSAGES` → `ValidationError`.
- `EMBEDDING_DIMENSIONS <= 0` → `ValidationError`.
- Несуществующий `AGENT_SYSTEM_PROMPT_PATH` → `ValidationError`.

### 3.2 Unit — LLM-клиент (`tests/services/test_llm_client.py`)

Обязательные сценарии:

- **Успех `chat`**: mock возвращает текст → возвращается строка.
- **Успех `embed`**: mock возвращает list[float] → возвращается список заданной длины.
- **Таймаут**: mock кидает `httpx.TimeoutException` → `LLMTimeout`.
- **Недоступность**: mock кидает `httpx.ConnectError` → `LLMUnavailable`.
- **HTTP 404 (модель не найдена)** → `LLMBadResponse`.
- **HTTP 5xx** → `LLMBadResponse`.
- **Пустой ответ** → `LLMBadResponse`.

### 3.3 Unit — парсер JSON ответа модели (`tests/agents/test_protocol.py`)

- Валидный action-ответ → `AgentDecision(kind="action", thought=..., action=..., args=...)`.
- Валидный final-ответ → `AgentDecision(kind="final", final_answer=...)`.
- Невалидный JSON → `LLMBadResponse`.
- Не объект (массив / строка) → `LLMBadResponse`.
- Смешанный формат (`thought` + `final_answer` одновременно) → `LLMBadResponse`.
- Пустой `thought` или `final_answer` → `LLMBadResponse`.
- `action` указан, `args` отсутствует → `LLMBadResponse`.

### 3.4 Unit — агентный цикл (`tests/agents/test_executor.py`)

Стратегия: мокать `OllamaClient` и `ToolRegistry`, проверять последовательность вызовов и финальный возврат.

- Финальный ответ на 1-м шаге → tools не вызывались.
- Финальный ответ на 3-м шаге → tools вызваны 2 раза с правильными аргументами; observation корректно прокинут в context.
- Tool кидает `ToolError` → observation = `Tool error: ...`, цикл продолжается.
- Битый JSON ответа → `LLMBadResponse`, цикл прерывается, возвращается специфичное сообщение.
- Превышение `AGENT_MAX_STEPS` → возвращается «не смог решить за N шагов».
- Превышение `AGENT_MAX_OUTPUT_CHARS` → `LLMBadResponse`.
- Логирование шагов: через `caplog` проверяем наличие `step=1`, `step=2`, ..., `kind=action`/`kind=final`.

### 3.5 Unit — реестр tools (`tests/tools/test_registry.py`)

- `get(name)` для несуществующего tool → `ToolNotFound`.
- `execute(name, args)` валидирует `args` по `args_schema` → `ArgsValidationError` при неподходящих args.
- `execute` логирует `tool=<name> dur_ms=<n> status=ok|error`.
- `execute` усекает output > `MAX_TOOL_OUTPUT_CHARS` суффиксом `... [truncated]`.
- `list_descriptions()` возвращает все зарегистрированные tools в стабильном порядке.

### 3.6 Unit — каждый tool

- `tests/tools/test_calculator.py`: `(123 + 456) * 2 → 1158`; `1 / 0 → ToolError`; неподдерживаемое выражение (`__import__`) → `ToolError`.
- `tests/tools/test_read_file.py`: путь в `data/` читается; путь вне whitelist → `ToolError`; `..` отклоняется; бинарный файл → `ToolError`; усечение длинных файлов.
- `tests/tools/test_http_request.py`: `httpx`-мок успех → строка с body; таймаут → `ToolError`; 404 — НЕ ошибка, отдаётся как часть строки.
- `tests/tools/test_web_search.py`: мок `ddgs.DDGS().text(...)` → JSON со списком результатов; пустой результат → `[]`; сетевой сбой → `ToolError`.
- `tests/tools/test_memory_search.py`: мок `OllamaClient.embed` + `SemanticMemory.search` → форматирование результата.
- `tests/tools/test_load_skill.py`: существующий скилл → тело без первой строки; несуществующий → `ToolError`.

### 3.7 Unit — `SemanticMemory` (`tests/services/test_memory.py`)

Это **редкий** случай, когда тест работает с **реальным** `sqlite-vec` (не мок) — потому что весь смысл слоя именно в том, как extension взаимодействует с sqlite. Используем `tmp_path` для `.db`-файла.

- `init()` идемпотентен (двойной вызов не ломает схему).
- `insert(text, vector, metadata)` пишет одну строку в `memory_chunks` и одну в `memory_vec`; rowid'ы совпадают.
- `search(vector, top_k=K, scope_user_id=U)` возвращает up-to-K строк, отсортированных по `distance`, фильтрует по `user_id`.
- `search` возвращает `[]` если БД пустая.
- При несовпадении размерности вектора и `EMBEDDING_DIMENSIONS` — `ValueError` (или специфичное исключение).

Если в окружении CI `sqlite-vec` не загружается — тест помечается `pytest.skip(reason="sqlite-vec extension not available")`.

### 3.8 Unit — `Archiver` (`tests/services/test_archiver.py`)

- `archive(...)` вызывает `Summarizer.summarize` один раз с историей.
- Чанкование: для саммари длиной 3000 символов и `chunk_size=1500, overlap=150` получаются 3 чанка с `chunk_index 0, 1, 2`.
- Для каждого чанка вызывается `OllamaClient.embed` с правильным текстом.
- Для каждого чанка вызывается `SemanticMemory.insert` с метаданными.
- Падение `Summarizer` → `Archiver` бросает понятную ошибку, **не** очищает store.
- Падение `embed` на втором чанке → транзакция откатывается (если решим использовать транзакции; иначе — все ранее вставленные чанки помечаются для отката).

### 3.9 Unit — `SkillRegistry` (`tests/services/test_skills.py`)

- Сканирование `tmp_path`-каталога с `<name>/SKILL.md` корректно находит все скиллы.
- Первая строка `Description: ...` парсится в `description`; остальное — в `body`.
- `list_descriptions()` возвращает `[{name, description}]`.
- `get_body(name)` для несуществующего → `KeyError` или `SkillNotFound`.
- `SKILL.md` без первой строки `Description:` → ошибка валидации при загрузке.

### 3.10 Unit — `PromptLoader` (`tests/services/test_prompts.py`)

- При старте читает указанный путь в строку.
- Несуществующий путь → `FileNotFoundError`.
- Подстановка `{{TOOLS_DESCRIPTION}}` корректна.
- Подстановка `{{SKILLS_DESCRIPTION}}` корректна.
- Если плейсхолдера нет в файле — подстановка пропускается без ошибки.

### 3.11 Unit — handlers Telegram (`tests/adapters/telegram/`)

Стратегия: **не поднимать реальный aiogram Dispatcher**, вызывать handler-функцию напрямую с мок-объектом `Message`.

- `test_commands.py`:
  - `/start` → `message.answer` вызван с приветствием.
  - `/help` → ответ содержит список команд + текущую модель + текущий промпт + список tools + список скиллов.
  - `/models` → ответ содержит имена моделей.
  - `/model qwen3.5:4b` → `registry.set_model` вызван корректно.
  - `/model unknown` → ответ «не найдена», `set_model` НЕ вызывался.
  - `/prompt текст` → `registry.set_prompt` вызван.
  - `/prompt` (без аргумента) → `registry.reset_prompt` вызван.
  - `/new` (пустая история) → ответ «сессия пустая», `Archiver.archive` НЕ вызывался, `rotate_conversation_id` вызван.
  - `/new` (непустая история) → `Archiver.archive` вызван, `clear` + `rotate_conversation_id` вызваны.
  - `/new` (падение архивирования) → ответ «не удалось», `clear` НЕ вызван.
  - `/reset` → `clear` + `registry.reset` + `rotate_conversation_id` вызваны.
- `test_messages.py`:
  - Успешный путь: `core.handle_user_task` мокается → возвращает «ответ» → `message.answer("ответ")`.
  - `LLMUnavailable` от executor → `message.answer(<сообщение>)`, `logger.error` вызван.
  - `LLMTimeout` → ветка с сообщением о таймауте.
  - `LLMBadResponse` (битый JSON) → ветка с сообщением «модель ответила в неожиданном формате».
  - Длинный ответ (> 4096) → вызывается разбивка (несколько `answer`).
  - Слишком длинный ввод → подсказка, `core.handle_user_task` НЕ вызывался.
- `test_errors.py`:
  - Глобальный handler ловит произвольное исключение, отвечает нейтральным сообщением, polling не падает.

Пример мок-фабрики `Message`:

```python
@pytest.fixture
def fake_message(mocker):
    m = mocker.MagicMock()
    m.from_user.id = 111
    m.chat.id = 111
    m.text = "hello"
    m.answer = mocker.AsyncMock()
    m.bot.send_chat_action = mocker.AsyncMock()
    return m
```

### 3.12 Smoke / e2e (опционально, вручную)

Не автоматизируем в MVP, но держим чек-лист:

- Реальный Telegram + реальная Ollama + реальный `sqlite-vec`.
- Отправить `/start`, текстовую задачу для калькулятора, проверить, что в логах виден цикл шагов.
- Отправить задачу для `read_file`, потом задачу для `web_search`.
- Отправить `/new`, проверить, что в `data/memory.db` появились чанки.
- В новой сессии задать вопрос про прошлое («что мы обсуждали раньше про X»), проверить, что агент использует `memory_search`.
- Остановить Ollama, отправить текст → бот должен ответить «LLM недоступна».

## 4. Моки внешних систем

| Система     | Как мокаем                                                                                |
|-------------|-------------------------------------------------------------------------------------------|
| Telegram    | Не трогаем реальный API; `Message`/`Bot` — `MagicMock`/`AsyncMock`.                       |
| Ollama HTTP | `mocker.patch.object(client, "chat", return_value=...)` / `client.embed`. Ноль сетевых вызовов. |
| `ddgs`      | `mocker.patch("ddgs.DDGS.text", return_value=[...])`.                                     |
| `httpx`     | `httpx.MockTransport` или `respx` для `http_request`-tool.                                |
| `sqlite-vec`| **Не мокаем** — поднимаем реальную БД на `tmp_path`. Если extension не грузится в окружении — `pytest.skip`. |
| Файлы логов | Временный каталог через `tmp_path`; не проверяем содержимое в CI, только что пишет.       |
| `_skills/`  | Подменяем путь на `tmp_path` с тестовыми `SKILL.md`.                                      |
| `_prompts/` | Подменяем путь на `tmp_path` с тестовыми markdown-файлами.                                |

## 5. Покрытие

- Цель на MVP: **70%+** по пакету `app/` (без `__main__.py` и `main.py`).
- Модули `services/`, `agents/`, `tools/` — **≥ 85%**.
- Модуль `app/agents/protocol.py` (парсер JSON) — **100%** (мал, но критичен).

## 6. Запуск

```bash
pytest -q
pytest -q --cov=app --cov-report=term-missing   # при установленном pytest-cov
pytest tests/agents -q -v                       # детально по подсистеме
pytest tests/tools -q -v
```

## 7. CI (опционально, не MVP)

Простой workflow GitHub Actions: `actions/setup-python@v5` → `pip install -r requirements.txt` → `pytest -q`. За рамками MVP, но структура тестов это позволяет (никаких сетевых запросов, нет реального Telegram, нет реальной Ollama; `sqlite-vec` либо доступен в runner'е, либо тесты-skip'ятся).

## 8. Что **не** покрываем тестами

- Реальный Telegram (визуальная проверка).
- Реальный Ollama (smoke-чек после деплоя).
- Скорость моделей (это not testable).
- Содержание `_skills/<name>/SKILL.md` (это контент, не код).
- Содержание `_prompts/agent_system.md` (это контент; покрываем `PromptLoader`, который его читает и подставляет плейсхолдеры).
