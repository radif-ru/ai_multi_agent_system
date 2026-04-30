# Спринт 03. Исправление багов и консольный режим

- **Источник:** Обратная связь пользователя (баги, таймауты, картинки, скиллы); `_docs/roadmap.md` Этап 5 (новые адаптеры).
- **Ветка:** `feature/03-bugs-and-console` (от `main`, после закрытия спринта 02).
- **Открыт:** 2026-04-30
- **Закрыт:** —

## 1. Цель спринта

Закрыть критические баги, мешающие использованию: таймауты при `/new` и долгих запросах, неработающие новые скиллы, потеря контекста картинок. Заложить фундамент для мульти-адаптерной архитектуры через консольный режим как «эталонный» адаптер.

## 2. Скоуп и non-goals

### В скоупе
- Диагностика и устранение таймаутов (§1.1, §2.1).
- Поддержка YAML frontmatter в скиллах (§1.4).
- Консольный адаптер с полным набором команд (§2.3).
- Выбор поисковика через команды (§3.1).
- Рекомендации по vision-моделям (§1.3).
- Обработка reply-сообщений в Telegram (§3.3).
- Форматирование кода для Telegram (§3.2).

### Вне скоупа (non-goals)
- Интеграция с внешними онлайн-чатами (GPT-4, Claude) — отдельный спринт.
- Hot-reload моделей (разогрев) — отдельный спринт.
- Web и MAX адаптеры — следующий спринт после консоли.
- Песочница (sandbox) для tools.

## 3. Acceptance Criteria спринта

- [ ] `/new` работает быстро или даёт понятный прогресс, нет таймаутов.
- [ ] Бот принимает новые скиллы (bash-linux, bash-pro, weather) без ошибок.
- [ ] Консольный режим запускается и поддерживает все команды Telegram.
- [ ] Команда для выбора поисковика работает в Telegram и консоли.
- [ ] Reply-сообщения в Telegram обрабатываются с контекстом.
- [ ] Код в ответах бота отформатирован для Telegram.
- [ ] Все задачи спринта — `Done`, сводная таблица актуальна.

---

## 4. Этап 1. Критические баги

Цель — устранить блокеры: таймауты, неработающие скиллы, проблемы с картинками.

### Задача 1.1. Диагностика и устранение таймаутов при `/new` и долгих запросах

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §5; `_docs/commands.md` §`/new`; `_docs/current-state.md`.
- **Затрагиваемые файлы:** `app/services/archiver.py`, `app/services/summarizer.py`, `app/adapters/telegram/handlers/commands.py`, `app/config.py`, `.env.example`.

#### Описание

Проблема: при `/new` долгое выполнение, часто таймаут. То же при долгих запросах агента.

Диагностика:
1. Добавить детальное логирование этапов `/new` (суммаризация, эмбеддинг, запись в БД).
2. Проверить, где теряется время (суммаризация длинных сессий, map-reduce, embedding чанков).

Решения:
- Возможно, `map-reduce` суммаризация создаёт слишком много вызовов LLM — оптимизировать размер батчей.
- Возможно, embedding чанков последовательный — сделать параллельным с ограничением concurrency.
- Возможно, таймаут Ollama слишком мал для больших моделей — добавить параметр таймаута для суммаризации.

#### Definition of Done

- [x] Логирование показывает время каждого этапа `/new` (суммаризация, чанкинг, embedding, запись).
- [x] Оптимизация: embedding чанков параллельный (asyncio.gather с семафором).
- [x] Команда `/new` показывает прогресс пользователю («Суммирую…», «Создаю эмбеддинги…») при длительности > 5 секунд.
- [x] Тест: `/new` на сессии из 50+ сообщений завершается < 30 секунд.
- [x] **Документация обновлена:** `_docs/architecture.md` §5, `_docs/commands.md` §`/new`.
- [x] **Тесты добавлены:** тест параллельного embedding, тест прогресса.
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.2. Проверка и оптимизация схемы SQLite

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` §5; `app/services/memory.py`.
- **Затрагиваемые файлы:** `app/services/memory.py`, `tests/services/test_memory.py`.

#### Описание

Проверить таблицу `memory_chunks`: лишние столбцы, foreign keys.

Текущая схема (из кода):
```sql
CREATE TABLE IF NOT EXISTS memory_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    chat_id         INTEGER NOT NULL,
    conversation_id TEXT    NOT NULL,
    chunk_index     INTEGER NOT NULL,
    created_at      TEXT    NOT NULL,
    text            TEXT    NOT NULL
);
```

Вопросы:
1. Нужен ли `chat_id` отдельно от `user_id`? В Telegram они связаны, но для других адаптеров — возможно нет.
2. Нужен ли foreign key? sqlite-vec использует `rowid`, связь через него.
3. Нужен ли индекс по `created_at` для старых чанков?

#### Definition of Done

- [ ] Проверена схема: `memory_chunks` + `memory_vec` (virtual table).
- [ ] Решение: оставить как есть или оптимизировать (убрать `chat_id` если избыточен, добавить индексы).
- [ ] Если изменения — миграция (пересоздание таблиц при старте с потерей старых данных — acceptable для MVP).
- [ ] **Документация обновлена:** `_docs/memory.md` §5 (схема таблиц).
- [ ] **Тесты обновлены:** проверка схемы после `init()`.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.3. Рекомендации по лёгким vision-моделям

- **Статус:** Progress
- **Приоритет:** high
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/current-state.md`; `_docs/architecture.md` §6.4; `app/services/vision.py`.
- **Затрагиваемые файлы:** `_docs/skills.md` или новый `_docs/vision-models.md`, `README.md`.

#### Описание

Рекомендовать лучшие лёгкие vision-модели для Ollama (локальный запуск).

Исследование:
- **moondream2** (~1.6B) — самая лёгкая, быстрая, но качество ниже.
- **llava-phi3** (~4B) — баланс скорости и качества.
- **minicpm-v** (~8B) — хорошее качество, работа с текстом на картинках (OCR).
- **gemma3:4b** — нативно мультимодальная, от Google, 4B параметров.
- **qwen2.5-vl:7b** — лучшее качество для структурированного анализа (таблицы, диаграммы).

Рекомендация по умолчанию: `gemma3:4b` или `llava-phi3`.

#### Definition of Done

- [ ] Документ сравнение моделей: размер, скорость, качество, use case.
- [ ] Обновить `.env.example`: закомментированный `VISION_MODEL=gemma3:4b` с пояснением.
- [ ] **Документация добавлена:** `_docs/vision-models.md` (или раздел в `_docs/stack.md`).
- [ ] Тесты: n/a (документация).
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.4. Поддержка YAML frontmatter в скиллах

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/skills.md` §3; `app/services/skills.py`.
- **Затрагиваемые файлы:** `app/services/skills.py`, `tests/services/test_skills.py`, `_docs/skills.md`.

#### Описание

Новые скиллы (`bash-linux`, `bash-pro`, `weather`) используют YAML frontmatter:
```yaml
---
name: bash-linux
description: "..."
risk: unknown
source: community
---
```

Старый парсер ожидает `Description:` в первой строке. Нужно поддержать оба формата:
1. Legacy: `Description: <text>` в первой строке.
2. YAML frontmatter: `---
description: "..."
---`.

#### Definition of Done

- [x] `SkillRegistry.load()` парсит оба формата (legacy и YAML frontmatter).
- [x] Для YAML frontmatter: извлекаем `description`, опционально `name`, `risk`, `source`.
- [x] Тест: скилл с YAML frontmatter загружается без ошибок.
- [x] Тест: legacy-скилл (`example-summary`) продолжает работать.
- [x] **Документация обновлена:** `_docs/skills.md` §3 (форматы SKILL.md), `_skills/README.md`.
- [x] **Тесты добавлены:** парсинг YAML frontmatter, fallback на legacy.
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.5. Сохранение контекста картинки для уточняющих вопросов

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.3
- **Связанные документы:** `_docs/architecture.md` §6.4; `app/adapters/telegram/handlers/messages.py`, `app/services/vision.py`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `app/services/conversation.py`, `_docs/architecture.md`.

#### Описание

Проблема: пользователь кидает картинку, агент описывает её. Пользователь спрашивает «а что там написано в углу?» — агент не понимает, т.к. видит только текстовое описание.

Решения (на выбор, обсудить):
1. **Сохранять base64 картинки в истории** — дорого по токенам, но точно работает.
2. **Сохранять путь к файлу** — временные файлы удаляются, нужно архивирование.
3. **Давать агенту tool для повторного анализа** — агент сам вызовет `describe_image` если нужно.

Выбранный подход: **№3** — добавить tool `describe_image`, который агент может вызвать. При первой загрузке картинки — описание + путь в `tmp/`. Если агенту нужны детали — он вызывает tool с путём.

#### Definition of Done

- [ ] Tool `describe_image(image_path: str) -> str` — вызывает `Vision.describe()`.
- [ ] Handler `handle_photo` передаёт в `goal` путь к файлу + описание.
- [ ] Временные файлы картинок **не удаляются сразу** — живут 1 час (или до `/new`).
- [ ] **Документация обновлена:** `_docs/architecture.md` §6.4, `_docs/tools.md`.
- [ ] **Тесты добавлены:** tool `describe_image`, handler с путём.
- [ ] `git status` чист, `pytest -q` зелёный.

---

## 5. Этап 2. Консольный адаптер

Цель — создать «эталонный» адаптер для работы с агентом без Telegram.

### Задача 2.1. Спецификация консольного режима

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §7.4; `_docs/commands.md`; `_docs/instructions.md` §0.
- **Затрагиваемые файлы:** `_docs/console-adapter.md` (новый), `_docs/architecture.md`.

#### Описание

Спецификация CLI-режима:
- Запуск: `python -m app.console` (отдельная entry point, не `__main__.py`).
- Поддержка всех команд Telegram: `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset` + текст.
- История диалога в памяти (как в Telegram).
- User ID фиксированный (например, `-1` для консоли).
- Выход по `/exit` или Ctrl+D.
- Форматирование: markdown (не HTML как в Telegram).

Архитектура:
- `app/adapters/console/` — пакет консольного адаптера.
- `ConsoleAdapter` класс — аналог `TelegramAdapter`, вызывает `core.handle_user_task`.
- Общие команды вынести в `app/commands/` (shared между Telegram и консолью).

#### Definition of Done

- [ ] Документ `_docs/console-adapter.md` со спецификацией.
- [ ] Обновить `_docs/architecture.md` §7.4 — упомянуть консольный адаптер как пример.
- [ ] Тесты: n/a (документация).
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 2.2. Вынос команд в общий модуль

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.1
- **Связанные документы:** `_docs/console-adapter.md`; `_docs/commands.md`; `app/adapters/telegram/handlers/commands.py`.
- **Затрагиваемые файлы:** `app/commands/__init__.py`, `app/commands/registry.py`, `app/adapters/telegram/handlers/commands.py` (рефакторинг).

#### Описание

Вынести логику команд из `telegram/handlers/commands.py` в общий модуль `app/commands/`:
- `CommandContext` — user_id, chat_id, conversations, archiver, settings и т.д.
- `CommandResult` — текст ответа + флаги (например, `clear_screen`).
- Каждая команда — функция `async def cmd_new(ctx: CommandContext) -> CommandResult`.

Telegram handler вызывает общую команду и отправляет результат через `message.answer()`.
Консольный adapter вызывает ту же команду и печатает в stdout.

#### Definition of Done

- [ ] Модуль `app/commands/` с `CommandContext`, `CommandResult`, `CommandRegistry`.
- [ ] Все команды (`/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`) вынесены в `app/commands/`.
- [ ] Telegram handler рефакторен: использует `app/commands/`.
- [ ] Тесты для команд работают (обновить `tests/adapters/telegram/test_commands.py`).
- [ ] **Документация обновлена:** `_docs/commands.md` (новая структура), `_docs/architecture.md`.
- [ ] **Тесты добавлены/обновлены:** `tests/commands/test_*.py`.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 2.3. Реализация консольного адаптера

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.2
- **Связанные документы:** `_docs/console-adapter.md`; `app/__main__.py`.
- **Затрагиваемые файлы:** `app/adapters/console/__init__.py`, `app/adapters/console/adapter.py`, `app/console_main.py`.

#### Описание

Реализовать консольный адаптер:
- `app/adapters/console/adapter.py` — `ConsoleAdapter` класс.
- `app/console_main.py` — точка входа `python -m app.console`.
- REPL цикл: читает строку → парсит команду/текст → вызывает `core.handle_user_task` → печатает ответ.
- Поддержка истории (readline/arrow keys) через `readline` модуль.
- Graceful shutdown по Ctrl+C / Ctrl+D.

#### Definition of Done

- [ ] `python -m app.console` запускается и работает REPL.
- [ ] Все команды `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset` работают.
- [ ] Текстовые сообщения обрабатываются через `core.handle_user_task`.
- [ ] История между сообщениями сохраняется (in-memory).
- [ ] **Документация обновлена:** `_docs/console-adapter.md`, `_docs/README.md` (навигация).
- [ ] **Тесты добавлены:** `tests/adapters/console/test_adapter.py` (моки stdin/stdout).
- [ ] `git status` чист, `pytest -q` зелёный.

---

## 6. Этап 3. Поисковик и форматирование

Цель — дать пользователю выбор поисковика и красивый вывод кода.

### Задача 3.1. Выбор поисковика через команды

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 2.2
- **Связанные документы:** `_docs/commands.md`; `_docs/stack.md` §9; `app/tools/web_search.py`.
- **Затрагиваемые файлы:** `app/config.py`, `app/commands/search_engine.py`, `app/tools/web_search.py`, `.env.example`.

#### Описание

Команды `/search_engines` (список) и `/search_engine <name>` (выбор активного).
Поисковики: `duckduckgo` (default), `bing`, `google` (требует API ключ), `brave`, `searxng`.

Хранение: `UserSettingsRegistry` (in-memory, как модель и системный промпт).
Tool `web_search` читает активный поисковик из контекста.

#### Definition of Done

- [ ] Команды `/search_engines`, `/search_engine <name>` в `app/commands/`.
- [ ] `UserSettingsRegistry` поддерживает `search_engine` per user.
- [ ] Tool `web_search` использует активный поисковик (fallback на `duckduckgo`).
- [ ] **Документация обновлена:** `_docs/commands.md` §«Выбор поисковика», `_docs/stack.md` §9.
- [ ] **Тесты добавлены:** команды, tool с разными поисковиками.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 3.2. Форматирование кода для Telegram

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/commands.md`; `app/adapters/telegram/handlers/messages.py`.
- **Затрагиваемые файлы:** `app/adapters/telegram/utils.py`, `app/adapters/telegram/handlers/messages.py`.

#### Описание

Когда агент возвращает код, оборачивать в Telegram-специфичное форматирование:
- Кодовые блоки markdown → HTML: ` ```python\n...\n``` ` → `<pre><code class="language-python">...</code></pre>`.
- Или использовать `ParseMode.MARKDOWN` для ответов с кодом.

Утилита `format_for_telegram(text: str) -> tuple[str, ParseMode]` — определяет, есть ли код, и выбирает parse_mode.

#### Definition of Done

- [ ] Утилита `format_for_telegram` в `app/adapters/telegram/utils.py`.
- [ ] Handler `messages.py` использует утилиту для выбора `ParseMode`.
- [ ] Код в ответах отображается с подсветкой синтаксиса в Telegram.
- [ ] **Документация обновлена:** `_docs/commands.md` (раздел «Форматирование»).
- [ ] **Тесты добавлены:** `tests/adapters/telegram/test_utils.py`.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 3.3. Обработка reply-сообщений в Telegram

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §4; `app/adapters/telegram/handlers/messages.py`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `tests/adapters/telegram/test_messages.py`.

#### Описание

Когда пользователь нажимает «Ответить» на сообщение — включать текст оригинального сообщения в контекст.

Формат:
```
[В ответ на: <текст оригинального сообщения>]
<текст ответа пользователя>
```

Если оригинал — длинный, обрезать до N символов.

#### Definition of Done

- [ ] Handler `handle_text` проверяет `message.reply_to_message`.
- [ ] Если есть reply — добавляет контекст оригинального сообщения.
- [ ] **Документация обновлена:** `_docs/architecture.md` §4, `_docs/commands.md`.
- [ ] **Тесты добавлены:** reply с текстом, reply с длинным текстом (обрезка).
- [ ] `git status` чист, `pytest -q` зелёный.

---

## 7. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | Консольный адаптер затягивается по срокам | Разбить на задачи 2.1–2.3, можно остановиться после 2.2 (инфраструктура) |
| 2 | Таймауты `/new` требуют архитектурных изменений | Начать с диагностики (логирование), потом оптимизация |
| 3 | YAML frontmatter сломает существующие скиллы | Поддержать оба формата, тесты на оба |
| 4 | Сохранение картинок занимает много места | TTL 1 час + cleanup job, ограничение размера tmp/ |

---

## 8. Сводная таблица задач спринта

| #   | Задача | Приоритет | Объём | Статус | Зависит от |
|-----|--------|:---------:|:-----:|:------:|:----------:|
| 1.1 | Диагностика и устранение таймаутов | high | M | Done | — |
| 1.2 | Проверка схемы SQLite | high | S | ToDo | — |
| 1.3 | Рекомендации vision-моделей | high | XS | Progress | — |
| 1.4 | Поддержка YAML frontmatter | high | S | Done | — |
| 1.5 | Контекст картинки для уточнений | high | M | ToDo | 1.3 |
| 2.1 | Спецификация консольного режима | high | S | ToDo | — |
| 2.2 | Вынос команд в общий модуль | high | M | ToDo | 2.1 |
| 2.3 | Реализация консольного адаптера | high | M | ToDo | 2.2 |
| 3.1 | Выбор поисковика | medium | S | ToDo | 2.2 |
| 3.2 | Форматирование кода | medium | XS | ToDo | — |
| 3.3 | Обработка reply | medium | S | ToDo | — |

---

## 9. История изменений спринта

- **2026-04-30** — спринт открыт, ветка `feature/03-bugs-and-console` создана от `main`.
- **2026-04-30** — задача 1.1 Done: диагностика и устранение таймаутов `/new` (логирование этапов, параллельный embedding, progress callback, EMBEDDING_CONCURRENCY).
- **2026-04-30** — задача 1.4 Done: поддержка YAML frontmatter в скиллах (bash-linux, bash-pro, weather), обратная совместимость с legacy форматом.
