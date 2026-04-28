# Внешние ссылки

Каталог ссылок на документацию используемых в проекте библиотек, моделей, протоколов и стандартов. Цель — не искать одно и то же повторно при работе над задачей. **Это не справочник по проекту**, а только указатели наружу.

При добавлении новой зависимости в `requirements.txt` или новой внешней системы — допишите сюда строку с краткой пометкой «зачем нужно в проекте» (модуль / функция / переменная окружения).

## 1. Telegram

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| aiogram (3.x) | https://docs.aiogram.dev/ | `app/main.py`, `app/adapters/telegram/handlers/*` — `Bot`, `Dispatcher`, `Router`, `BaseMiddleware` |
| aiogram — Filters | https://docs.aiogram.dev/en/latest/dispatcher/filters/index.html | `app/adapters/telegram/handlers/messages.py` — `F.text & ~F.text.startswith("/")` |
| aiogram — Errors | https://docs.aiogram.dev/en/latest/dispatcher/errors.html | `app/adapters/telegram/handlers/errors.py` — `@router.errors(...)` |
| aiogram — `setMyCommands` | https://core.telegram.org/bots/api#setmycommands | `app/main.py::main` — список команд BotFather |
| Telegram Bot API | https://core.telegram.org/bots/api | общая спецификация (long polling, лимиты) |
| Telegram message limit (4096) | https://core.telegram.org/method/messages.sendMessage | `app/utils/text.py::TELEGRAM_MESSAGE_LIMIT` |
| BotFather | https://t.me/BotFather | получение `TELEGRAM_BOT_TOKEN` |

## 2. LLM-слой (Ollama)

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| Ollama | https://ollama.com/ | LLM-рантайм, REST API на `localhost:11434`, см. `_docs/stack.md` §3 |
| Ollama REST API | https://github.com/ollama/ollama/blob/main/docs/api.md | базовый протокол (`/api/chat`, `/api/embeddings`) |
| Ollama Python SDK | https://github.com/ollama/ollama-python | `app/services/llm.py` — `ollama.AsyncClient`, `ollama.ResponseError` |
| Модель `qwen3.5:4b` | https://ollama.com/library/qwen | значение `OLLAMA_DEFAULT_MODEL` по умолчанию |
| Модель `nomic-embed-text` | https://ollama.com/library/nomic-embed-text | значение `EMBEDDING_MODEL` по умолчанию |
| httpx (исключения) | https://www.python-httpx.org/exceptions/ | `app/services/llm.py` — маппинг `TimeoutException`, `ConnectError` в `LLMError` |

## 3. Векторная БД

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| sqlite-vec | https://github.com/asg017/sqlite-vec | `app/services/memory.py` — `sqlite_vec.load(connection)`, `vec0` virtual table |
| sqlite-vec docs | https://alexgarcia.xyz/sqlite-vec/ | референс синтаксиса `vec0`, `MATCH` |
| sqlite-vec Python | https://alexgarcia.xyz/sqlite-vec/python.html | загрузка extension в `sqlite3.Connection` |
| История: sqlite-vss (предшественник) | https://github.com/asg017/sqlite-vss | для контекста; в проекте не используется |

## 4. Поиск

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| ddgs (бывшая duckduckgo-search) | https://pypi.org/project/ddgs/ | `app/tools/web_search.py` — `DDGS().text(...)` |

## 5. HTTP

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| httpx | https://www.python-httpx.org/ | `app/tools/http_request.py` — `httpx.AsyncClient.get(...)` |

## 6. Конфигурация и логирование

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| pydantic | https://docs.pydantic.dev/latest/ | `field_validator`, `model_validator`, `SecretStr` в `app/config.py` |
| pydantic-settings | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ | `app/config.py::Settings(BaseSettings)`, парсинг `.env` |
| Python `logging` | https://docs.python.org/3/library/logging.html | `app/logging_config.py`, логгеры во всех модулях |
| Python `logging.handlers` | https://docs.python.org/3/library/logging.handlers.html | `RotatingFileHandler` в `app/logging_config.py` |
| `logging.config.dictConfig` | https://docs.python.org/3/library/logging.config.html#logging.config.dictConfig | конфигурация логирования через словарь |
| Python `sqlite3` | https://docs.python.org/3/library/sqlite3.html | базовый драйвер для `sqlite-vec` |

## 7. Тестирование

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| pytest | https://docs.pytest.org/ | основной test-runner, конфиг в `pyproject.toml` |
| pytest-asyncio | https://pytest-asyncio.readthedocs.io/ | `asyncio_mode = "auto"` в `pyproject.toml`, тесты `async def` |
| pytest-mock | https://pytest-mock.readthedocs.io/ | фикстура `mocker` в `tests/**/test_*.py` |
| `unittest.mock` | https://docs.python.org/3/library/unittest.mock.html | `MagicMock`, `AsyncMock` для мок-объектов |

## 8. Стандарты разработки

| Что | Ссылка | Где в проекте |
|-----|--------|---------------|
| Conventional Commits | https://www.conventionalcommits.org/ | формат коммитов: `feat(scope): ...`, см. `_docs/instructions.md` §1 |
| Python typing | https://docs.python.org/3/library/typing.html | type hints обязательны в публичном API |
| PEP 8 | https://peps.python.org/pep-0008/ | базовый стиль кода, `ruff` его реализует |
| `asyncio` | https://docs.python.org/3/library/asyncio.html | модель параллелизма для всего I/O |
| ruff | https://docs.astral.sh/ruff/ | целевой линтер/форматтер (опционально, не обязателен для MVP) |

## 9. Связанные репозитории автора

| Что | Ссылка | Что общего |
|-----|--------|-----------|
| ai_tg_bot (предыдущий проект автора) | https://github.com/radif-ru/ai_tg_bot | Структура `_docs/`, `_board/`, шаблоны спринтов и задач, дисциплина коммитов и тестов — переиспользованы и расширены здесь под мульти-агентную архитектуру. |
