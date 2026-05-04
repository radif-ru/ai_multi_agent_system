# Консольный адаптер

Консольный адаптер — «эталонный» пример реализации адаптера для работы с агентом без Telegram. Демонстрирует минимальный контракт адаптера с `core.handle_user_task` и может служить шаблоном для других адаптеров (web, MAX).

## 1. Запуск

```bash
ollama serve & .venv/bin/python -m app.console_main
```

Отдельная entry point через `app/console_main.py` (который запускает консольный адаптер, в отличие от `app/main.py` для Telegram-бота).

## 2. Поддерживаемые команды

Все команды Telegram-бота (кроме файловых операций):

| Команда      | Назначение                                                   |
|--------------|--------------------------------------------------------------|
| `/start`     | Приветствие, краткая инструкция, список команд.              |
| `/help`      | Подробная справка.                                           |
| `/models`    | Список доступных LLM + отметка активной.                     |
| `/model`     | Переключить активную LLM.                                    |
| `/prompt`    | Установить системный промпт (без аргумента — сброс).         |
| `/new`       | Архивировать сессию и открыть новую.                        |
| `/reset`     | Очистить in-memory историю + сбросить per-user настройки.    |
| `/exit`      | Выход из консоли (консольная команда, аналога в Telegram нет). |
| *любой текст* | Запустить агентный цикл с задачей.                           |

## 3. User ID и chat_id

Для консоли фиксированные идентификаторы:

- `user_id = -1` (для консоли)
- `chat_id = -1` (для консоли)

Это позволяет использовать существующие сервисы (`ConversationStore`, `UserSettingsRegistry`, `SemanticMemory`) без изменений.

## 4. История диалога

История хранится in-memory через `ConversationStore` (как в Telegram). При рестарте консоли история теряется. Для сохранения между сессиями используйте `/new` (архивирование в `sqlite-vec`).

## 5. Форматирование вывода

- Markdown (не HTML как в Telegram).
- Кодовые блоки выводятся как есть (```python ... ```), без конвертации в HTML.

## 6. REPL-цикл

```
> <ввод>
<ответ агента>
> <ввод>
<ответ агента>
...
> /exit
```

История ввода поддерживается через модуль `readline` (стрелки вверх/вниз для навигации по истории команд).

## 7. Graceful shutdown

- `Ctrl+D` (EOF) — выход.
- `Ctrl+C` — прерывание текущего запроса (если агент не начал выполнение), затем выход.
- `/exit` — явный выход.

При shutdown корректно закрываются клиенты (Ollama, SQLite-соединение).

## 8. Архитектура

### 8.1 Структура файлов

```
app/adapters/console/
├── __init__.py
└── adapter.py          # ConsoleAdapter класс

app/
└── console_main.py      # Точка входа python -m app.console_main
```

### 8.2 ConsoleAdapter

Аналог `TelegramAdapter`, но без aiogram:

```python
class ConsoleAdapter:
    def __init__(self, executor, conversations, archiver, user_settings, ...):
        self.executor = executor
        self.conversations = conversations
        self.archiver = archiver
        self.user_settings = user_settings
        self.user_id = -1
        self.chat_id = -1

    async def handle_input(self, text: str) -> str:
        # Проверка команды
        # Вызов core.handle_user_task или команды
        # Возврат ответа
```

### 8.3 Общие команды

Команды вынесены в общий модуль `app/commands/` (см. задачу 2.2). Консольный адаптер вызывает те же функции, что и Telegram-адаптер:

```python
from app.commands import CommandContext, CommandRegistry, cmd_start, cmd_help, ...

async def run_repl():
    ctx = CommandContext(
        user_id=-1,
        chat_id=-1,
        conversations=conversations,
        archiver=archiver,
        user_settings=user_settings,
        ...
    )
    
    while True:
        line = input("> ")
        if line == "/exit":
            break
        
        # Проверка команды
        if line.startswith("/"):
            cmd_name = line[1:].split()[0]
            result = await CommandRegistry.execute(cmd_name, ctx, line)
            print(result.text)
        else:
            # Текстовое сообщение
            response = await core.handle_user_task(line, user_id=-1, chat_id=-1, ...)
            print(response)
```

## 9. Ограничения

- Нет поддержки файлов (Document, Voice, Photo) — это специфика Telegram-адаптера.
- Нет reply-сообщений (консоль не поддерживает UI для reply).
- Нет разбиения длинных сообщений на части (консольный вывод не имеет лимита 4096 символов как Telegram).

## 10. Связанные документы

- `_docs/architecture.md` §8.4 — новый адаптер (web, MAX).
- `_docs/commands.md` — спецификация команд.
- `_docs/instructions.md` §1 — язык проекта.
