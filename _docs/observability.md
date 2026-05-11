# Наблюдаемость

Единый раздел про логи, трассировку и (в следующих задачах спринта 06) error tracking. Источник истины по коду — `app/logging_config.py`, `app/utils/tracing.py`, `app/middlewares/logging_mw.py`.

## 1. Структурные JSON-логи

Все логи приложения — валидные JSON-объекты, по одной записи на строку. Формирует `JsonFormatter` (`app/logging_config.py`), подключён как к `StreamHandler` (консоль), так и к `RotatingFileHandler` (файл `LOG_FILE`, по умолчанию `logs/agent.log`).

### Формат записи

```json
{
  "timestamp": "2026-05-11T12:34:56.123456+00:00",
  "level": "INFO",
  "service": "ai-multi-agent-system",
  "name": "app.services.llm",
  "message": "llm kind=chat model=qwen3.5:4b len_in=...",
  "trace_id": "a1b2c3d4e5f6",
  "user_id": 12345,
  "extra": { "duration_ms": 420, "status": "ok" }
}
```

Поля:

- `timestamp` — ISO-8601 UTC, с микросекундами.
- `level` — `DEBUG | INFO | WARNING | ERROR | CRITICAL`.
- `service` — константа `ai-multi-agent-system`.
- `name` — имя логгера (обычно `__name__` модуля).
- `message` — собственно текст записи.
- `trace_id` — короткий (12 hex) идентификатор текущего внешнего действия. `null`, если контекст не установлен.
- `user_id` — идентификатор пользователя, если биндится на этом уровне (`null` иначе).
- `extra` — произвольные поля, переданные через `logger.info(..., extra={"duration_ms": 42})`. Стандартные атрибуты `LogRecord` исключаются автоматически.
- `exc_info` / `stack_info` — текстовый дамп исключения / стека, если есть.

### Проверка

```bash
jq -c . < logs/agent.log | head -5
```

Если строка невалидна — `jq` завершится ошибкой.

## 2. Трассировка (`trace_id`)

`app/utils/tracing.py` хранит `trace_id` и `user_id` в `contextvars.ContextVar`. Это даёт автоматическую изоляцию по `asyncio.Task`: каждая корутина, обрабатывающая отдельное сообщение, получает свой идентификатор, а параллельные обработки не перемешиваются.

API:

```python
from app.utils.tracing import new_trace_id, bind_trace_id, reset_trace_id, get_trace_id
from app.utils.tracing import bind_user_id, reset_user_id

trace_token = bind_trace_id(new_trace_id())
user_token = bind_user_id(user_id)
try:
    ...  # вся обработка: handler → executor → llm → tools
finally:
    reset_user_id(user_token)
    reset_trace_id(trace_token)
```

`ContextFilter` (`app/logging_config.py`) автоматически подмешивает значения в каждую запись лога. Прокидывать их вручную через `extra=` не нужно; это имеет смысл только чтобы явно переопределить (например, в фоновой задаче с другим trace_id).

Где устанавливается:

- **Telegram**: `LoggingMiddleware` (`app/middlewares/logging_mw.py`) — на каждый `Update` генерируется новый `trace_id` и биндится `user_id`; оба сбрасываются в `finally` (в том числе при исключении в handler).
- **Console adapter**: `ConsoleAdapter.run` (`app/adapters/console/adapter.py`) — на каждую введённую команду или текст свежий `trace_id`, сбрасывается после обработки.
- **Фоновая архивация (recovery)**: планируется как отдельная задача (см. спринт 06 этап 4.3 / будущие спринты) — пока `recover_pending_journals` пишет логи без `trace_id` (`null`).

## 3. Границы внешних вызовов

Все сервисы, дёргающие внешние ресурсы, пишут согласованные записи вокруг каждого вызова:

- `external.call service=<name> ...` — перед вызовом (info).
- `external.ok service=<name> dur_ms=<n> ...` — успешное завершение (info).
- `external.fail service=<name> dur_ms=<n> error=<str> ...` — ошибка (error).

Поля в `extra`: `service`, `duration_ms`, `status`, плюс сервис-специфичные (`model`, `host`, `engine`, `http_status`, `len_in/len_out`, `n_results` …). Сырые payload'ы и сами ответы LLM/поиска в логи не попадают.

Точки установки (`grep -n external.call app`):

- `app/services/llm.py` — `service=ollama`, `kind=chat|embed`.
- `app/services/transcribe.py` — `service=transcribe`.
- `app/services/vision.py` — `service=vision`.
- `app/services/ocr.py` — `service=ocr`.
- `app/tools/http_request.py` — `service=http_request`, `host`.
- `app/tools/web_search.py` — `service=web_search`, `engine`.

## 4. Маскирование секретов

`app/utils/secrets.py::mask_secrets(d)` рекурсивно заменяет значения секретных ключей на `"***"`:

- Ключи, содержащие `token`, `secret`, `password`, `passwd`, `api_key`/`apikey`, `authorization`.
- Точные имена `auth`, `bearer`, `key`, `x-api-key` (регистронезависимо).

Использовать **перед** тем как положить структуру в `extra=` (или при логировании заголовков/конфигов). URL и тела HTTP-ответов по текущим настройкам в логи не пишутся — тем самым заголовок `Authorization` туда не уезжает. Тесты: `tests/utils/test_secrets.py`.

## 5. Error tracking (GlitchTip / Sentry)

`app/observability/__init__.py::setup_sentry(settings)` — единственная точка инициализации `sentry-sdk`. Вызывается в `app/main.py::main` и `app/console_main.py::main` сразу после `setup_logging(settings)`. Если `SENTRY_DSN` пуст (по умолчанию) — функция ничего не делает, `sentry_sdk.init(...)` не вызывается, сеть не дёргается; бот стартует как обычно.

### Конфигурация (`.env`)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `SENTRY_DSN` | *(пусто)* | DSN self-hosted GlitchTip (Sentry-совместимый). Пустое значение = error tracking выключен. |
| `SENTRY_ENVIRONMENT` | `dev` | Тег `event.environment`: `dev` / `staging` / `prod`. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Доля запросов с performance-трассировкой. По умолчанию только ошибки, без performance. |

Глобальные флаги `send_default_pii=False` и хук `before_send` (см. ниже) — зашиты в коде, не конфигурируются.

### Хук `before_send`

`app.observability._before_send(event, hint)` обогащает каждое событие перед отправкой:

- `trace_id` из `contextvars` (см. §2) → `event.tags.trace_id` и `event.extra.trace_id`;
- `user_id` из `contextvars` → `event.user.id` (строкой).

Возврат `None` (который бы отменил отправку) не используется: хук не фильтрует события, только обогащает. Если контекст пуст — возвращается исходный event без изменений.

### Интеграции

`LoggingIntegration(level=INFO, event_level=ERROR)` — все `logger.error(...)` и `logger.exception(...)` автоматически уезжают в GlitchTip как события; уровни `INFO/WARNING` идут в breadcrumbs и доезжают вместе со следующим event.

### Проверка через ошибки

(см. задачу 5.3 спринта 06) — тесты в `tests/observability/test_setup_sentry.py` + планируемые smoke-кейсы на четыре класса ошибок (ручная, асинхронная, внешний вызов, данные).
