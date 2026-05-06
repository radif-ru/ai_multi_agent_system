# Безопасность

Документ описывает меры защиты от типичных атак на LLM-системы, реализованные в проекте.

## 1. InputSanitizer

`InputSanitizer` — модуль для санитайзинга пользовательского ввода и защиты от prompt injection.

### 1.1 Функция `sanitize_user_input`

Функция находится в `app/security/input_sanitizer.py`.

**Сигнатура:**
```python
def sanitize_user_input(
    text: str,
    user_id: str | int | None = None,
    mode: Literal["log", "filter", "warn"] = "warn",
) -> str
```

**Параметры:**
- `text` — пользовательский ввод для проверки.
- `user_id` — идентификатор пользователя для логирования (опционально).
- `mode` — режим обработки:
  - `"log"` — только логировать WARNING, текст возвращать как есть.
  - `"filter"` — удалить подозрительные паттерны из текста.
  - `"warn"` — вернуть исходный текст с префиксом-предупреждением (по умолчанию).

**Возвращает:** очищенный или исходный текст в зависимости от режима.

### 1.2 Обнаруживаемые паттерны

Функция детектирует следующие паттерны prompt injection:

1. `"ignore all previous instructions"` / `"ignore previous instructions"` — попытка заставить модель проигнорировать системный промпт.
2. `"repeat your system prompt"` / `"print your instructions"` — попытка получить системный промпт.
3. `"forget everything above"` / `"disregard all above"` — попытка сбросить контекст.
4. `"system:"` / `"SYSTEM:"` в начале строки — попытка внедрить системную инструкцию.
5. `"<|"` / `"|>"` — разделители сообщений (часто используются для инъекций).

### 1.3 Интеграция

`InputSanitizer` интегрирован в Telegram-хендлеры и консольный адаптер в точках входа пользовательского текста перед передачей в `core.handle_user_task`.

**Точки интеграции:**
- `app/adapters/telegram/handlers/messages.py` — обработчик текстовых сообщений, документов, голосовых и фото.
- `app/adapters/console/adapter.py` — консольный адаптер.

Во всех точках используется режим `"warn"` — текст возвращается с префиксом-предупреждением при обнаружении паттернов.

См. задачу 3.2 спринта 05.

## 2. FileIdMapper

`FileIdMapper` — класс для маскирования путей к файлам во избежание data leakage.

**Сигнатура:**
```python
class FileIdMapper:
    def generate_id(file_path: Path) -> str
    def get_path(file_id: str) -> Path | None
```

**Методы:**
- `generate_id(file_path)` — генерирует уникальный временный ID для файла (например, `file_abc123`).
- `get_path(file_id)` — возвращает путь по ID или `None`, если ID не найден.

**Хранилище:** in-memory dict.

См. задачу 4.1 спринта 05.

## 3. ResponseSanitizer

`ResponseSanitizer` — модуль для фильтрации системной информации в ответах модели.

**Сигнатура:**
```python
def sanitize_response(text: str) -> str
```

**Обнаруживаемые паттерны:**
- Полные пути к файлам.
- Конфигурационные ключи.
- Фрагменты системного промпта.

См. задачу 7.1 спринта 05.

## 4. Защита Tools

### 4.1 Allowlist для опасных tools

Опасные tools (`http_request`, `read_file`, `read_document`) имеют дополнительную валидацию через allowlist в конфигурации.

**Параметр конфигурации:**
```python
dangerous_tools_allowlist: list[str]  # список разрешённых опасных tools
```

Если tool в списке опасных и не в allowlist — `ToolRegistry.execute` возвращает ошибку в observation.

См. задачу 6.1 спринта 05.

### 4.2 Валидация параметров опасных tools

Дополнительная валидация параметров:
- `http_request` — запрет на `file://`, `ftp://` и другие небезопасные протоколы.
- `read_file` / `read_document` — запрет на чтение системных путей (`/etc/`, `/sys/`, `/proc/`, `~/.ssh/`), проверка на path traversal (`../`).

См. задачу 6.2 спринта 05.

## 5. Усиление System Prompt

В системный промпт (`_prompts/agent_system.md`) добавлен раздел "Правила безопасности" с инструкциями:

- Запрет на игнорирование инструкций.
- Запрет на вывод системного промпта.
- Запрет на выполнение опасных операций без явного запроса.

См. задачу 5.1 спринта 05.

## 6. Архитектура

Модуль безопасности находится в `app/security/`:

```
app/security/
├── __init__.py
├── input_sanitizer.py
├── file_id_mapper.py
└── response_sanitizer.py
```

Интеграция в архитектуру:
- Хендлеры (Telegram, Console) → `InputSanitizer` → `core.handle_user_task`.
- Хендлеры файлов → `FileIdMapper` → goal с временными ID.
- Tools → проверка allowlist → валидация параметров.
- Executor → `ResponseSanitizer` → final_answer.

См. `_docs/architecture.md` §3.
